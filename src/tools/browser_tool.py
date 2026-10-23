"""Real browser control through the Chrome DevTools Protocol.

Nyx drives Microsoft Edge or Google Chrome over CDP: navigate, read the rendered
page text, click, type, wait for selectors and capture screenshots. The browser
starts on demand with an isolated profile and its own debugging port. Only
http/https URLs are accepted, and page scripts are treated as data, never as
instructions for Nyx.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import socket
import subprocess
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from core.operation_control import OperationCancelled
from tools.browser_locators import ACTIONABLE, RESOLVE, clean_locator

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 8000
MAX_SELECTOR_CHARS = 500
MAX_TYPE_CHARS = 2000
ALLOWED_SCHEMES = ("http://", "https://")
SENSITIVE_ACTIONS = {"click", "type"}

_BROWSER_CANDIDATES = (
    os.environ.get("NYX_BROWSER_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


class BrowserError(RuntimeError):
    """A browser action failed; the message is safe to show to the user."""


def find_browser() -> Path | None:
    for candidate in _BROWSER_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def validate_url(url: object) -> str:
    """Accept only absolute http(s) URLs; reject scripts, files and empty input."""
    text = str(url or "").strip()
    if not text:
        raise BrowserError("Informe uma URL http(s) para abrir.")
    if len(text) > 2048:
        raise BrowserError("URL longa demais.")
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme.lower() not in ("http", "https"):
        raise BrowserError("Só posso abrir endereços http:// ou https://.")
    if not parsed.netloc:
        raise BrowserError("A URL precisa de um domínio válido.")
    return text


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class BrowserSession:
    """One isolated browser instance plus the tab Nyx is driving."""

    def __init__(
        self,
        browser_path: Path | str | None = None,
        headless: bool = True,
        timeout: float = 25.0,
        control=None,
    ) -> None:
        self.browser_path = Path(browser_path) if browser_path else find_browser()
        self.headless = headless
        self.timeout = timeout
        from core.operation_control import OperationControl
        self.control = control or OperationControl()
        self._process: subprocess.Popen | None = None
        self._profile: str | None = None
        self._port = 0
        self._ws = None
        self._ws_url = ""
        self._message_id = 0
        self._started = False

    # -- lifecycle ---------------------------------------------------------
    @property
    def started(self) -> bool:
        return self._started and self._process is not None and self._process.poll() is None

    def start(self) -> None:
        self.control.check()
        if self.started:
            return
        if self.browser_path is None or not Path(self.browser_path).is_file():
            raise BrowserError(
                "Não encontrei Edge ou Chrome instalado. Instale um navegador Chromium ou defina NYX_BROWSER_PATH."
            )
        self._port = _free_port()
        self._profile = tempfile.mkdtemp(prefix="nyx-browser-")
        flags = [
            str(self.browser_path),
            f"--remote-debugging-port={self._port}",
            f"--user-data-dir={self._profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
            "--window-size=1280,900",
        ]
        if self.headless:
            flags.append("--headless=new")
        flags.append("about:blank")
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if self.headless else 0
        try:
            self._process = subprocess.Popen(
                flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation,
            )
        except OSError as exc:
            raise BrowserError(f"Falha ao iniciar o navegador: {exc}") from exc
        try:
            self._wait_for_devtools()
            self._started = True
            self._open_tab()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            log.debug("Falha ao fechar o WebSocket do navegador", exc_info=True)
        self._ws = None
        self._ws_url = ""
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            self._terminate_tree(process)
        # Chromium can leave renderer/GPU children behind when the root exits;
        # they all carry the unique profile path, so clean those up precisely.
        self._kill_profile_orphans()
        if self._profile:
            shutil.rmtree(self._profile, ignore_errors=True)
            self._profile = None
        self._started = False

    def _terminate_tree(self, process: subprocess.Popen) -> None:
        try:
            import psutil

            parent = psutil.Process(process.pid)
            for child in parent.children(recursive=True):
                try:
                    child.terminate()
                except psutil.Error:
                    pass
            parent.terminate()
            parent.wait(timeout=8)
        except Exception:
            try:
                process.terminate()
                process.wait(timeout=8)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    log.debug("Não foi possível encerrar o navegador", exc_info=True)

    def _kill_profile_orphans(self) -> None:
        if not self._profile:
            return
        try:
            import psutil
        except ImportError:
            return
        marker = self._profile.casefold()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = str(proc.info.get("name") or "").casefold()
                cmdline = " ".join(proc.info.get("cmdline") or []).casefold()
            except (psutil.Error, TypeError):
                continue
            if name in {"msedge.exe", "chrome.exe", "chromium", "chromium-browser"} and marker in cmdline:
                try:
                    proc.kill()
                except psutil.Error:
                    pass

    # -- transport ---------------------------------------------------------
    def _devtools(self, path: str) -> object:
        self.control.check()
        url = f"http://127.0.0.1:{self._port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                body = response.read(2 * 1024 * 1024).decode("utf-8")
                if path.startswith(("/json/activate/", "/json/close/")):
                    return body
                return json.loads(body or "{}")
        except (OSError, ValueError) as exc:
            raise BrowserError(f"O navegador não respondeu em {path}: {exc}") from exc

    def _wait_for_devtools(self) -> None:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            self.control.check()
            if self._process is not None and self._process.poll() is not None:
                raise BrowserError(f"O navegador encerrou durante a inicialização (código {self._process.returncode}).")
            try:
                self._devtools("/json/version")
                return
            except BrowserError:
                time.sleep(0.2)
        raise BrowserError("O navegador não abriu a porta de depuração a tempo.")

    def _open_tab(self, url: str = "about:blank") -> None:
        target = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
        data = self._devtools_put(f"/json/new?{target}")
        ws_url = str(data.get("webSocketDebuggerUrl") or "")
        if not ws_url:
            raise BrowserError("O navegador não forneceu uma aba depurável.")
        self._ws_url = ws_url
        self._connect()

    def _devtools_put(self, path: str) -> dict:
        self.control.check()
        url = f"http://127.0.0.1:{self._port}{path}"
        request = urllib.request.Request(url, data=b"", method="PUT")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except (OSError, ValueError) as exc:
            raise BrowserError(f"O navegador recusou abrir a aba: {exc}") from exc

    def _connect(self) -> None:
        try:
            import websocket  # type: ignore

            self._ws = websocket.create_connection(self._ws_url, timeout=self.timeout, suppress_origin=True)
            self._ws.settimeout(0.25)
        except Exception as exc:
            raise BrowserError(f"Não consegui falar com o navegador: {exc}") from exc

    def _call(self, method: str, params: dict | None = None) -> dict:
        from websocket import WebSocketTimeoutException
        self.control.check()
        if not self.started:
            self.start()
        self._message_id += 1
        message_id = self._message_id
        payload = json.dumps({"id": message_id, "method": method, "params": params or {}})
        try:
            self._ws.send(payload)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                self.control.check()
                try:
                    raw = self._ws.recv()
                except (TimeoutError, WebSocketTimeoutException):
                    continue
                if not raw:
                    continue
                data = json.loads(raw)
                if data.get("id") != message_id:
                    continue
                if "error" in data:
                    error = data["error"]
                    raise BrowserError(f"{method} falhou: {error.get('message', error)}")
                return data.get("result", {})
        except (BrowserError, OperationCancelled):
            raise
        except Exception as exc:
            raise BrowserError(f"Falha de comunicação com o navegador: {exc}") from exc
        raise BrowserError(f"{method} não respondeu a tempo.")

    def _evaluate(self, expression: str) -> object:
        result = self._call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        if "exceptionDetails" in result:
            detail = result["exceptionDetails"]
            raise BrowserError(f"A página recusou a ação: {detail.get('text', 'erro de script')}")
        return result.get("result", {}).get("value")

    # -- actions -----------------------------------------------------------
    def open(self, url: str) -> dict:
        target = validate_url(url)
        self.start()
        self._call("Page.enable")
        self._call("Runtime.enable")
        navigation = self._call("Page.navigate", {"url": target})
        if navigation.get("errorText"):
            raise BrowserError(f"Navegação recusada: {navigation['errorText']}")
        if navigation.get("isDownload"):
            raise BrowserError("O endereço iniciou um download; nenhuma página carregada foi verificada.")
        self._wait_loaded(expected_url=target, loader_id=navigation.get("loaderId"))
        return self.status()

    def navigate(self, url: str) -> dict:
        return self.open(url)

    def _wait_loaded(self, timeout: float | None = None, expected_url: str | None = None,
                     loader_id: str | None = None) -> None:
        deadline = time.monotonic() + (timeout or self.timeout)
        while time.monotonic() < deadline:
            self.control.check()
            try:
                frame = self._call("Page.getFrameTree").get("frameTree", {}).get("frame", {})
                state = self.status()
            except BrowserError:
                state = None
                frame = {}
            committed = (frame.get("loaderId") == loader_id if loader_id else
                         not expected_url or state and state.get("url") == expected_url)
            if isinstance(state, dict) and state.get("ready") == "complete" and (
                committed and state.get("url") == frame.get("url")
            ):
                return
            time.sleep(0.2)
        raise BrowserError("A página não terminou de carregar a tempo.")

    def status(self) -> dict:
        info = self._evaluate(
            "(() => ({title: document.title, url: location.href, ready: document.readyState}))()"
        )
        return info if isinstance(info, dict) else {}

    def read_text(self) -> dict:
        info = self._evaluate(
            "(() => ({title: document.title, url: location.href, "
            "text: document.body ? document.body.innerText : ''}))()"
        )
        if not isinstance(info, dict):
            raise BrowserError("Não consegui ler o conteúdo da página.")
        text = str(info.get("text") or "")
        truncated = len(text) > MAX_TEXT_CHARS
        info["text"] = text[:MAX_TEXT_CHARS]
        info["truncated"] = truncated
        info["chars"] = len(text)
        return info

    def _resolve(self, selector) -> str:
        try:
            locator = clean_locator(selector)
        except ValueError as exc:
            raise BrowserError(str(exc)) from exc
        result = self._call("Runtime.evaluate", {"expression": RESOLVE + "(" + json.dumps(locator) + ")",
                                                 "returnByValue": False})
        if result.get("exceptionDetails"):
            detail = result["exceptionDetails"].get("exception", {}).get("description", "Alvo indisponível.")
            raise BrowserError(str(detail).split("\n")[0])
        object_id = result.get("result", {}).get("objectId")
        if not object_id:
            raise BrowserError("Não foi possível confirmar o alvo.")
        return object_id

    def _on_element(self, object_id, function, *args):
        result = self._call("Runtime.callFunctionOn", {"objectId": object_id,
            "functionDeclaration": function, "arguments": [{"value": v} for v in args], "returnByValue": True})
        if result.get("exceptionDetails"):
            detail = result["exceptionDetails"].get("exception", {}).get("description", "Alvo indisponível.")
            raise BrowserError(str(detail).split("\n")[0])
        return result.get("result", {}).get("value")

    def _target_point(self, object_id, editable=False):
        first = self._on_element(object_id, ACTIONABLE, editable)
        time.sleep(0.1)
        second = self._on_element(object_id, ACTIONABLE, editable)
        if not isinstance(first, dict) or not isinstance(second, dict) or any(
            abs(first[k] - second[k]) > 1 for k in ("x", "y", "width", "height")
        ):
            raise BrowserError("O alvo ainda está em movimento; inspecione novamente antes de agir.")
        return {k: second[k] for k in ("x", "y")}

    def _release_element(self, object_id):
        if not self.control.is_cancelled():
            try:
                self._call("Runtime.releaseObject", {"objectId": object_id})
            except BrowserError:
                pass

    def click(self, selector) -> str:
        object_id = self._resolve(selector)
        try:
            point = self._target_point(object_id)
            self._call("Input.dispatchMouseEvent", {"type": "mousePressed", "button": "left", "clickCount": 1, **point})
            self._call("Input.dispatchMouseEvent", {"type": "mouseReleased", "button": "left", "clickCount": 1, **point})
            return "clicked"
        finally:
            self._release_element(object_id)

    def type_text(self, selector, text: str) -> str:
        value = str(text or "")
        if len(value) > MAX_TYPE_CHARS:
            raise BrowserError("Texto excede o limite; nenhuma digitação realizada.")
        object_id = self._resolve(selector)
        try:
            self._target_point(object_id, editable=True)
            focused = self._on_element(object_id, "function() { this.focus(); return document.activeElement === this; }")
            if not focused:
                raise BrowserError("O campo não recebeu foco.")
            self._call("Input.dispatchKeyEvent", {"type": "keyDown", "modifiers": 2, "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65})
            self._call("Input.dispatchKeyEvent", {"type": "keyUp", "modifiers": 2, "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65})
            self._call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Backspace", "windowsVirtualKeyCode": 8})
            self._call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "windowsVirtualKeyCode": 8})
            if value:
                self._call("Input.insertText", {"text": value})
            if not self._on_element(object_id, "function(value) { return this.isConnected && this.value === value; }", value):
                raise BrowserError("O conteúdo do campo não corresponde ao texto solicitado; não repeti a entrada.")
            return "typed"
        finally:
            self._release_element(object_id)

    def wait_for(self, selector: str, timeout: float = 10.0) -> bool:
        selector = _clean_selector(selector)
        deadline = time.monotonic() + min(max(1.0, timeout), 60.0)
        expression = "document.querySelector(%s) !== null" % json.dumps(selector)
        while time.monotonic() < deadline:
            if self._evaluate(expression):
                return True
            time.sleep(0.15)
        raise BrowserError(f"O elemento {selector!r} não apareceu a tempo.")

    def screenshot(self, path: Path) -> Path:
        result = self._call("Page.captureScreenshot", {"format": "png"})
        data = result.get("data")
        if not data:
            raise BrowserError("O navegador não devolveu a captura.")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(base64.b64decode(data))
        return destination

    def extract_links(self, selector: str | None = None, limit: int = 50) -> list[dict]:
        clean_limit = max(1, min(int(limit or 50), 200))
        sel_json = json.dumps(_clean_selector(selector)) if selector else "null"
        expr = """(() => {
            const root = %s ? document.querySelector(%s) : document;
            if (!root) return [];
            const elements = Array.from(root.querySelectorAll("a[href]"));
            const seen = new Set();
            const results = [];
            for (const el of elements) {
                const href = el.href;
                const text = (el.innerText || el.textContent || "").trim();
                if (!href || href.startsWith("javascript:") || href.startsWith("data:")) continue;
                const key = href + "::" + text;
                if (seen.has(key)) continue;
                seen.add(key);
                results.push({text: text.slice(0, 200), href: href.slice(0, 1000)});
                if (results.length >= %d) break;
            }
            return results;
        })()""" % (sel_json, sel_json, clean_limit)
        items = self._evaluate(expr)
        return items if isinstance(items, list) else []

    def extract_tables(self, limit: int = 10) -> list[dict]:
        clean_limit = max(1, min(int(limit or 10), 30))
        expr = """(() => {
            const tables = Array.from(document.querySelectorAll("table")).slice(0, %d);
            return tables.map(table => {
                const headers = Array.from(table.querySelectorAll("th")).map(th => (th.innerText || "").trim().slice(0, 100));
                const rows = Array.from(table.querySelectorAll("tr"))
                    .map(tr => Array.from(tr.querySelectorAll("td")).map(td => (td.innerText || "").trim().slice(0, 200)))
                    .filter(r => r.length > 0)
                    .slice(0, 100);
                return {headers, rows};
            });
        })()""" % clean_limit
        tables = self._evaluate(expr)
        return tables if isinstance(tables, list) else []

    def wait_for_text(self, text: str, timeout: float = 10.0) -> bool:
        clean_text = str(text or "").strip()
        if not clean_text:
            raise BrowserError("Informe o texto a ser aguardado.")
        deadline = time.monotonic() + min(max(1.0, timeout), 60.0)
        expr = """(() => {
            return Boolean(document.body && (document.body.innerText || "").includes(%s));
        })()""" % json.dumps(clean_text)
        while time.monotonic() < deadline:
            if self._evaluate(expr):
                return True
            time.sleep(0.15)
        raise BrowserError(f"O texto {clean_text!r} não apareceu a tempo.")

    def scroll(
        self,
        direction: str = "down",
        amount: int = 500,
        selector: str | None = None,
    ) -> dict:
        sel_json = json.dumps(_clean_selector(selector)) if selector else "null"
        dir_json = json.dumps(str(direction or "down").lower())
        expr = """(() => {
            if (%s) {
                const el = document.querySelector(%s);
                if (!el) return {found: false};
                el.scrollIntoView({behavior: "instant", block: "center"});
                return {
                    found: true,
                    scrollY: window.scrollY,
                    scrollHeight: document.documentElement.scrollHeight
                };
            }
            const dir = %s;
            const amount = Number(%d) || 500;
            if (dir === "top") window.scrollTo(0, 0);
            else if (dir === "bottom") window.scrollTo(0, document.documentElement.scrollHeight);
            else if (dir === "up") window.scrollBy(0, -amount);
            else window.scrollBy(0, amount);
            const scrollY = window.scrollY;
            const scrollHeight = document.documentElement.scrollHeight;
            const clientHeight = document.documentElement.clientHeight;
            return {
                found: true,
                scrollY,
                scrollHeight,
                clientHeight,
                atBottom: (scrollY + clientHeight >= scrollHeight - 5)
            };
        })()""" % (sel_json, sel_json, dir_json, amount)
        res = self._evaluate(expr)
        if isinstance(res, dict) and not res.get("found", True):
            raise BrowserError(f"Elemento {selector!r} não encontrado para rolagem.")
        return res if isinstance(res, dict) else {}

    def list_tabs(self) -> list[dict]:
        if not self.started:
            self.start()
        raw = self._devtools("/json/list")
        if not isinstance(raw, list):
            return []
        tabs = []
        for item in raw:
            if isinstance(item, dict) and item.get("type") == "page":
                tabs.append({
                    "id": str(item.get("id") or ""),
                    "title": str(item.get("title") or ""),
                    "url": str(item.get("url") or ""),
                    "active": item.get("webSocketDebuggerUrl") == self._ws_url,
                })
        return tabs

    def new_tab(self, url: str = "about:blank") -> dict:
        if not self.started:
            self.start()
        target = validate_url(url) if url and url != "about:blank" else "about:blank"
        data = self._devtools_put("/json/new?about:blank")
        ws_url = str(data.get("webSocketDebuggerUrl") or "")
        if not ws_url:
            raise BrowserError("O navegador não abriu a nova aba.")
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._ws_url = ws_url
        self._connect()
        self._call("Page.enable")
        self._call("Runtime.enable")
        if target != "about:blank":
            return self.open(target)
        return self.status()

    def switch_tab(self, tab_id: str) -> dict:
        if not self.started:
            self.start()
        clean_id = str(tab_id or "").strip()
        if not clean_id:
            raise BrowserError("Informe o ID da aba para alternar.")
        raw = self._devtools("/json/list")
        if not isinstance(raw, list):
            raise BrowserError("Não foi possível listar as abas.")
        target = next((item for item in raw if isinstance(item, dict) and item.get("type") == "page"
                       and str(item.get("id")) == clean_id), None)
        if not target:
            raise BrowserError(f"Aba {clean_id} não encontrada.")
        ws_url = str(target.get("webSocketDebuggerUrl") or "")
        if not ws_url:
            raise BrowserError("Aba selecionada não suporta conexão de depuração.")
        self._devtools(f"/json/activate/{clean_id}")
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._ws_url = ws_url
        self._connect()
        self._call("Page.enable")
        self._call("Runtime.enable")
        return self.status()

    def close_tab(self, tab_id: str | None = None) -> dict:
        if not self.started:
            raise BrowserError("Nenhum navegador em execução.")
        raw = self._devtools("/json/list")
        if not isinstance(raw, list):
            raise BrowserError("Não foi possível listar as abas.")
        pages = [item for item in raw if isinstance(item, dict) and item.get("type") == "page"]
        if not pages:
            raise BrowserError("Nenhuma aba aberta.")
        target_id = str(tab_id or "").strip()
        if not target_id:
            current = next((p for p in pages if p.get("webSocketDebuggerUrl") == self._ws_url), pages[0])
            target_id = str(current.get("id") or "")
        if target_id not in {str(page.get("id")) for page in pages}:
            raise BrowserError("Aba não pertence à sessão controlada.")
        try:
            self._devtools(f"/json/close/{target_id}")
        except Exception as exc:
            raise BrowserError(f"Falha ao fechar aba {target_id}: {exc}") from exc
        remaining = [p for p in pages if str(p.get("id")) != target_id]
        if remaining:
            selected = next((p for p in remaining if p.get("webSocketDebuggerUrl") == self._ws_url), remaining[0])
            new_ws = str(selected.get("webSocketDebuggerUrl") or "")
            if new_ws:
                if self._ws is not None:
                    try:
                        self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                self._ws_url = new_ws
                self._connect()
                self._call("Page.enable")
                self._call("Runtime.enable")
                return self.status()
        self.close()
        return {"status": "closed", "remaining_tabs": 0}


def _clean_selector(selector: object) -> str:
    text = str(selector or "").strip()
    if not text:
        raise BrowserError("Informe um seletor CSS.")
    if len(text) > MAX_SELECTOR_CHARS:
        raise BrowserError("Seletor longo demais.")
    return text


def is_sensitive_action(action: object) -> bool:
    """Clicking and typing can change account state, so they ask first."""
    return str(action or "").strip().lower() in SENSITIVE_ACTIONS


_SELF_CHECK_HTML = b"""<!doctype html><html><head><meta charset="utf-8"><title>Nyx browser check</title></head>
<body><h1 id="status">inicial</h1><input id="name"><button id="go"
onclick="document.getElementById('status').textContent = 'Clicado: ' + document.getElementById('name').value">Enviar</button>
<a href="http://127.0.0.1:9999/docs">Documentacao</a>
<table><tr><th>Header</th></tr><tr><td>Dado</td></tr></table>
<div style="height: 1200px;"></div>
<p id="bottom">Fim da pagina</p>
</body></html>"""


def browser_self_check() -> dict:
    """Drive a local page end to end; used by the packaged application check."""
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(_SELF_CHECK_HTML)))
            self.end_headers()
            self.wfile.write(_SELF_CHECK_HTML)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    session = BrowserSession(headless=True)
    report: dict = {"browser": str(find_browser() or ""), "url": url, "ok": False}
    try:
        session.open(url)
        session.wait_for("#go", timeout=5)
        session.type_text("#name", "Nyx")
        session.click("#go")
        session.wait_for_text("Clicado: Nyx", timeout=5)
        text = session.read_text()["text"]
        links = session.extract_links()
        tables = session.extract_tables()
        scroll_res = session.scroll("down", amount=300)
        report["text"] = text
        report["links_count"] = len(links)
        report["tables_count"] = len(tables)
        report["scroll_ok"] = bool(scroll_res.get("found"))
        report["ok"] = "Clicado: Nyx" in text and len(links) >= 1 and len(tables) >= 1
    except BrowserError as exc:
        report["error"] = str(exc)
    finally:
        session.close()
        server.shutdown()
        server.server_close()
    return report


def make_browser_tool_func(session: BrowserSession, allowed_roots: list[Path] | None = None):
    """Turn the session into a registry tool: one action per call."""
    roots = [Path(root).resolve() for root in (allowed_roots or [])]

    def run(params: dict):
        from tools.registry import ToolResult

        action = str(params.get("action") or "").strip().lower()
        try:
            if action in {"open", "navigate"}:
                info = session.open(str(params.get("url") or ""))
                return ToolResult(True, json.dumps(info, ensure_ascii=False),
                                  meta={"action": action, "url": info.get("url", "")})
            if action == "read":
                info = session.read_text()
                return ToolResult(True, info["text"],
                                  meta={"action": "read", "url": info.get("url", ""),
                                        "title": info.get("title", ""), "chars": info.get("chars", 0),
                                        "truncated": info.get("truncated", False)})
            if action == "click":
                selector = params.get("locator") or _clean_selector(params.get("selector"))
                session.click(selector)
                expected_text = params.get("expected_text")
                if expected_text:
                    session.wait_for_text(str(expected_text), float(params.get("timeout") or 10))
                return ToolResult(True, session.read_text()["text"],
                                  meta={"action": "click", "selector": selector,
                                        "dispatched": True, "verified": bool(expected_text),
                                        "check": "expected_text" if expected_text else "dispatch_only"})
            if action == "type":
                selector = params.get("locator") or _clean_selector(params.get("selector"))
                session.type_text(selector, str(params.get("text") or ""))
                return ToolResult(True, f"Texto digitado e conferido em {selector}.",
                                  meta={"action": "type", "verified": True, "check": "field_value"})
            if action == "wait":
                selector = _clean_selector(params.get("selector"))
                session.wait_for(selector, float(params.get("timeout") or 10))
                return ToolResult(True, f"Elemento {selector} disponível.", meta={"action": "wait"})
            if action == "screenshot":
                target = Path(params.get("path") or "") if params.get("path") else None
                if target is not None:
                    resolved = target.resolve()
                    if not roots or not any(
                        resolved == root or root in resolved.parents for root in roots
                    ):
                        return ToolResult(False, error="A captura só pode ser salva dentro das pastas permitidas.")
                    target = resolved
                else:
                    stamp = time.strftime("%Y%m%d-%H%M%S")
                    target = (roots[0] / "browser" / f"shot-{stamp}.png") if roots else Path(f"shot-{stamp}.png")
                saved = session.screenshot(target)
                return ToolResult(True, str(saved), meta={"action": "screenshot", "path": str(saved)})
            if action == "status":
                info = session.status()
                return ToolResult(True, json.dumps(info, ensure_ascii=False), meta={"action": "status"})
            if action in {"links", "extract_links"}:
                selector = params.get("selector")
                limit = int(params.get("limit") or 50)
                links = session.extract_links(selector=selector, limit=limit)
                return ToolResult(True, json.dumps(links, ensure_ascii=False, indent=2),
                                  meta={"action": "links", "count": len(links)})
            if action in {"tables", "extract_tables"}:
                limit = int(params.get("limit") or 10)
                tables = session.extract_tables(limit=limit)
                return ToolResult(True, json.dumps(tables, ensure_ascii=False, indent=2),
                                  meta={"action": "tables", "count": len(tables)})
            if action == "wait_text":
                text = str(params.get("text") or "")
                timeout = float(params.get("timeout") or 10)
                session.wait_for_text(text, timeout)
                return ToolResult(True, f"Texto {text!r} disponível.", meta={"action": "wait_text"})
            if action == "scroll":
                direction = str(params.get("direction") or "down")
                amount = int(params.get("amount") or 500)
                selector = params.get("selector")
                res = session.scroll(direction=direction, amount=amount, selector=selector)
                return ToolResult(True, json.dumps(res, ensure_ascii=False), meta={"action": "scroll"})
            if action in {"tabs", "list_tabs"}:
                tabs = session.list_tabs()
                return ToolResult(True, json.dumps(tabs, ensure_ascii=False, indent=2),
                                  meta={"action": "tabs", "count": len(tabs)})
            if action == "new_tab":
                url = str(params.get("url") or "about:blank")
                tab = session.new_tab(url)
                return ToolResult(True, json.dumps(tab, ensure_ascii=False), meta={"action": "new_tab"})
            if action == "switch_tab":
                tab_id = str(params.get("tab_id") or params.get("id") or "")
                tab = session.switch_tab(tab_id)
                return ToolResult(True, json.dumps(tab, ensure_ascii=False), meta={"action": "switch_tab"})
            if action == "close_tab":
                tab_id = params.get("tab_id") or params.get("id")
                tab = session.close_tab(tab_id)
                return ToolResult(True, json.dumps(tab, ensure_ascii=False), meta={"action": "close_tab"})
            if action == "close":
                session.close()
                return ToolResult(True, "Navegador encerrado.", meta={"action": "close"})
            return ToolResult(False, error=f"Ação de navegador desconhecida: {action!r}")
        except (BrowserError, OperationCancelled) as exc:
            return ToolResult(False, error=str(exc), meta={"action": action})
        except (OSError, ValueError) as exc:
            return ToolResult(False, error=f"Falha no navegador: {exc}", meta={"action": action})

    return run
