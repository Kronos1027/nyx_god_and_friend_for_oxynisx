"""Nyx — tools/ui_tool.py (Fase 4: Automação Segura de UI)

Automação desktop para Windows 11:
- pywinauto e pygetwindow para inspeção e controle de janelas.
- pyautogui para screenshots, cliques e digitação com failsafe ativo.
- Sempre auditado e protegido pela matriz de permissões.
"""

from __future__ import annotations

import logging
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from tools.registry import ToolResult

log = logging.getLogger(__name__)


class UITool:
    """Automação de interface de usuário no Windows com verificações de segurança."""

    def __init__(self, screenshots_dir: Path | str | None = None, control=None) -> None:
        from core.operation_control import OperationControl
        self.control = control or OperationControl()
        self.screenshots_dir = (
            Path(screenshots_dir) if screenshots_dir else Path("assets/screenshots")
        )
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        from tools.windows_client import WindowsAutomationClient
        self.targets = WindowsAutomationClient(self.control)

    def is_destructive(self, action: str, params: dict) -> bool:
        """Determina se uma ação de UI é considerada potencialmente destrutiva."""
        # Fechar janelas ou combinações de teclas forçadas (Alt+F4, etc.) são destrutivas
        if action in ("close_window", "kill_window", "close_app", "kill_process", "terminate_process"):
            return True
        if action == "press_key":
            key = str(params.get("key", "")).lower()
            if key in ("alt+f4", "ctrl+w", "ctrl+q") or "delete" in key.split("+"):
                return True
        return False

    def list_windows(self, params: dict | None = None) -> ToolResult:
        """Lista todas as janelas visíveis com título no Windows."""
        try:
            import pygetwindow as gw

            all_windows = gw.getAllWindows()
            visible = [
                w.title.strip()
                for w in all_windows
                if w.title and w.title.strip() and w.visible
            ]
            # Remove duplicatas preservando ordem
            unique_visible = list(dict.fromkeys(visible))
            identities = [{"title": w.title, "hwnd": w._hWnd} for w in all_windows
                          if w.title and w.title.strip() and w.visible]
            from tools.windows_targets import window_identity
            for entry in identities:
                try:
                    window = next(w for w in all_windows if w._hWnd == entry["hwnd"])
                    _, pid, created = window_identity(window)
                    entry.update(pid=pid, created=created)
                except Exception:
                    continue
            return ToolResult(
                ok=True,
                output=json.dumps(identities, ensure_ascii=False)
                if unique_visible
                else "Nenhuma janela visível encontrada.",
                meta={"count": len(identities), "windows": identities},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao listar janelas: {exc}")

    def focus_window(self, params: dict) -> ToolResult:
        try:
            info = self.targets.call("focus", params)
            return ToolResult(True, f"Janela focalizada: '{info['title']}'", meta=info)
        except Exception as exc:
            return ToolResult(False, error=f"Foco não confirmado: {exc}",
                              meta={"outcome_unknown": getattr(exc, "outcome_unknown", False)})

    def _window_state(self, params, minimized):
        try:
            from tools.windows_targets import select_window
            window = select_window(params)
            self.control.check()
            (window.minimize if minimized else window.maximize)()
            verified = window.isMinimized if minimized else window.isMaximized
            return ToolResult(True, "Estado de janela observado.", meta={"hwnd": window._hWnd,
                "verified": bool(verified), "check": "window_state"})
        except Exception as exc:
            return ToolResult(False, error=f"Estado de janela não confirmado: {exc}")

    def minimize_window(self, params: dict) -> ToolResult:
        return self._window_state(params, True)

    def maximize_window(self, params: dict) -> ToolResult:
        return self._window_state(params, False)

    @staticmethod
    def get_dpi_scale() -> float:
        """Obtém o fator de escala de DPI do Windows (ex: 1.0 = 100%, 1.25 = 125%)."""
        try:
            import ctypes
            dpi = ctypes.windll.user32.GetDpiForSystem()
            return max(1.0, float(dpi) / 96.0)
        except Exception:
            return 1.0

    def take_screenshot(self, params: dict | None = None) -> ToolResult:
        """Capture a selected monitor or window in physical pixels, on demand."""
        params = params or {}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = str(params.get("filename") or f"screenshot_{stamp}.png")
        if not filename.endswith(".png"):
            filename += ".png"
        if Path(filename).name != filename or ":" in filename or "\\" in filename:
            return ToolResult(False, error="Use apenas um nome de arquivo PNG dentro da pasta de capturas.")
        target_path = (self.screenshots_dir / filename).resolve()
        if self.screenshots_dir.resolve() not in target_path.parents:
            return ToolResult(False, error="Caminho de captura fora da pasta permitida.")
        try:
            import mss
            import mss.tools
            from tools.windows_targets import physical_pixels, select_window
            self.control.check()
            with physical_pixels(), mss.MSS() as capture:
                index = int(params.get("monitor", 1))
                if not 0 <= index < len(capture.monitors):
                    raise ValueError("Monitor não encontrado.")
                region = dict(capture.monitors[index])
                hwnd = None
                if params.get("hwnd") is not None or params.get("title"):
                    window = select_window(params)
                    if window.isMinimized:
                        raise ValueError("Restaure a janela antes de capturá-la.")
                    hwnd = window._hWnd
                    region = {"left": window.left, "top": window.top,
                              "width": window.width, "height": window.height}
                shot = capture.grab(region)
                self.control.check()
                mss.tools.to_png(shot.rgb, shot.size, output=str(target_path))
                return ToolResult(True, f"Captura salva: {target_path}", meta={"path": str(target_path),
                    "width": shot.width, "height": shot.height, "left": region["left"], "top": region["top"],
                    "monitor": index, "hwnd": hwnd, "coordinate_space": "physical_pixels", "engine": "mss"})
        except Exception as exc:
            return ToolResult(False, error=f"Falha ao capturar a região solicitada: {exc}")

    def click_coordinate(self, params: dict) -> ToolResult:
        """Clica nas coordenadas (x, y) da tela."""
        x = params.get("x")
        y = params.get("y")
        button = str(params.get("button", "left")).lower()
        if x is None or y is None:
            return ToolResult(ok=False, error="Coordenadas 'x' e 'y' são obrigatórias.")

        try:
            import pyautogui
            import win32gui
            from tools.windows_targets import physical_pixels, select_window

            pyautogui.FAILSAFE = True
            with physical_pixels():
                window = select_window(params)
                focused = self.focus_window({"hwnd": window._hWnd})
                if not focused.ok:
                    return focused
                if not (window.left <= int(x) < window.right and window.top <= int(y) < window.bottom):
                    raise ValueError("Coordenada fora da janela escolhida.")
                hit = win32gui.WindowFromPoint((int(x), int(y)))
                if win32gui.GetAncestor(hit, 2) != window._hWnd:
                    raise ValueError("Coordenada coberta por outra janela; nenhum clique realizado.")
                self.control.check()
                pyautogui.click(x=int(x), y=int(y), button=button)
            return ToolResult(
                ok=True,
                output=f"Clique ({button}) executado em ({x}, {y}).",
                meta={"x": x, "y": y, "button": button, "verified": False, "check": "dispatch_only"},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao clicar: {exc}")

    def type_text(self, params: dict) -> ToolResult:
        """Address an inspected Edit control without overwriting the clipboard."""
        return self.element_action("type_element", params)

    def press_key(self, params: dict) -> ToolResult:
        """Pressiona uma tecla ou combinação de teclas."""
        key = params.get("key")
        if not key:
            return ToolResult(ok=False, error="Parâmetro 'key' é obrigatório.")

        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            focused = self.focus_window(params)
            if not focused.ok:
                return focused
            self.control.check()
            key_str = str(key).lower().strip()
            if "+" in key_str:
                parts = [p.strip() for p in key_str.split("+")]
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(key_str)
            return ToolResult(
                ok=True, output=f"Tecla '{key_str}' acionada.", meta={"key": key_str}
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao pressionar tecla: {exc}")

    def open_url(self, params: dict) -> ToolResult:
        """Abre uma URL ou site no navegador padrão do Windows."""
        url = str(params.get("url", params.get("link", params.get("target", "")))).strip()
        if not url:
            app_name = str(params.get("app", "")).lower()
            service_map = {
                "spotify": "https://open.spotify.com",
                "youtube": "https://www.youtube.com",
                "github": "https://github.com",
                "gmail": "https://mail.google.com",
                "whatsapp": "https://web.whatsapp.com",
            }
            url = service_map.get(app_name, "")
            if not url:
                return ToolResult(ok=False, error="Parâmetro 'url' é obrigatório.")

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        import webbrowser
        try:
            browser = getattr(self, "browser_session", None)
            if browser is not None:
                info = browser.open(url)
                return ToolResult(True, json.dumps(info, ensure_ascii=False),
                                  meta={"url": info.get("url"), "verified": True, "check": "controlled_navigation"})
            if not webbrowser.open(url):
                return ToolResult(False, error="O Windows não confirmou a abertura do navegador.")
            return ToolResult(ok=True, output=f"Pedido enviado ao navegador: '{url}'", meta={"url": url, "verified": False})
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao abrir URL '{url}': {exc}")

    def inspect_elements(self, params: dict | None = None) -> ToolResult:
        """Inspect only the chosen or active window, with an expiring identity."""
        try:
            info = self.targets.inspect(params or {})
            return ToolResult(True, json.dumps(info, ensure_ascii=False), meta=info)
        except Exception as exc:
            return ToolResult(False, error=f"Inspeção UIA indisponível: {exc}")

    def element_action(self, action, params):
        try:
            info = self.targets.act(action, params)
            return ToolResult(True, json.dumps(info, ensure_ascii=False), meta=info)
        except Exception as exc:
            return ToolResult(False, error=f"Ação UIA não confirmada: {exc}",
                              meta={"outcome_unknown": getattr(exc, "outcome_unknown", False)})

    def click_element(self, params: dict) -> ToolResult:
        return self.element_action("click_element", params)

    def kill_process(self, params: dict) -> ToolResult:
        """Terminate one explicitly identified process, never substring matches."""
        if params.get("pid") is None or params.get("created") is None:
            return ToolResult(False, error="É obrigatório informar pid e created retornados por list_windows.")
        try:
            import psutil
            pid = int(params["pid"])
            if pid <= 4 or pid == os.getpid():
                raise ValueError("Este processo não pode ser encerrado por esta ferramenta.")
            process = psutil.Process(pid)
            if process.create_time() != float(params["created"]):
                raise ValueError("O PID foi reutilizado; obtenha uma nova identificação antes de confirmar.")
            self.control.check()
            process.terminate()
            try:
                process.wait(timeout=2)
                verified = True
            except psutil.TimeoutExpired:
                verified = False
            return ToolResult(True, "Pedido de encerramento enviado ao processo identificado.",
                              meta={"pid": pid, "verified": verified, "check": "process_exited"})
        except Exception as exc:
            return ToolResult(False, error=f"Encerramento de processo não confirmado: {exc}")

    def list_running_apps(self, params: dict | None = None) -> ToolResult:
        """Varre e lista as janelas de aplicativos visíveis do usuário no Windows 11."""
        try:
            import pygetwindow as gw
            all_wins = gw.getAllWindows()
            apps = []
            system_ignore = {
                "program manager",
                "default ime",
                "msctfime ui",
                "settings",
                "windows input experience",
            }
            for w in all_wins:
                title = (w.title or "").strip()
                if not title or title.lower() in system_ignore:
                    continue
                # Ignora janelas invisíveis ou de tamanho minúsculo
                if getattr(w, "width", 100) <= 10 or getattr(w, "height", 100) <= 10:
                    continue
                apps.append({
                    "title": title,
                    "x": getattr(w, "left", 0),
                    "y": getattr(w, "top", 0),
                    "width": getattr(w, "width", 0),
                    "height": getattr(w, "height", 0),
                    "is_active": getattr(w, "isActive", False),
                })

            if not apps:
                titles = [t.strip() for t in gw.getAllTitles() if t.strip() and t.strip().lower() not in system_ignore]
                if titles:
                    return ToolResult(
                        ok=True,
                        output="Aplicativos/Janelas detectados:\n" + "\n".join(f"- {t}" for t in titles[:15]),
                        meta={"apps": titles[:15], "count": len(titles)},
                    )
                return ToolResult(
                    ok=True,
                    output="Aplicativos em execução: Nenhum aplicativo com janela aberta visível detectado.",
                    meta={"apps": []},
                )

            formatted = []
            for app in apps:
                status = " [EM FOCO]" if app["is_active"] else ""
                formatted.append(f"- {app['title']}{status}")

            return ToolResult(
                ok=True,
                output=f"Aplicativos em execução ({len(apps)} abertos):\n" + "\n".join(formatted),
                meta={"apps": apps, "count": len(apps)},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao listar aplicativos abertos: {exc}")

    def close_app(self, params: dict) -> ToolResult:
        """Request close on one window; an unsaved-data dialog remains unverified."""
        try:
            import win32gui
            from tools.windows_targets import select_window
            target = dict(params)
            target["title"] = params.get("title") or params.get("app") or params.get("name") or ""
            window = select_window(target)
            self.control.check()
            window.close()
            verified = not win32gui.IsWindow(window._hWnd)
            return ToolResult(True, "Pedido de fechamento enviado; confirme eventuais diálogos do aplicativo.",
                meta={"hwnd": window._hWnd, "verified": verified, "check": "window_closed"})
        except Exception as exc:
            return ToolResult(False, error=f"Fechamento não confirmado: {exc}")

    def screen_vision(self, params: dict | None = None) -> ToolResult:
        """Captura screenshot e analisa o conteúdo visual com o modelo moondream via Ollama."""
        params = params or {}
        prompt = params.get(
            "prompt",
            params.get("question", "Descreva o que está visível na tela e liste os principais aplicativos ou textos."),
        )

        res_shot = self.take_screenshot(params)
        if not res_shot.ok or "path" not in res_shot.meta:
            return ToolResult(ok=False, error=f"Falha ao obter screenshot para visão: {res_shot.error}")

        img_path = res_shot.meta["path"]
        try:
            import base64
            from core.runtime_budget import post_ollama_json

            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "model": "moondream:1.8b",
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
            }
            host = os.environ.get("NYX_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
            data = post_ollama_json(f"{host}/api/generate", payload, timeout=25.0)
            description = data.get("response", "").strip()

            return ToolResult(
                ok=True,
                output=f"Análise Visual da Tela ({img_path}):\n{description}",
                meta={"image_path": img_path, "description": description},
            )
        except Exception as exc:
            return ToolResult(
                ok=False,
                error=f"Falha na análise visual com Moondream: {exc}. Screenshot salvo em {img_path}.",
            )

    def open_app(self, params: dict) -> ToolResult:
        """Abre um aplicativo instalado e observa sua janela real."""
        app_name = str(params.get("app") or params.get("name") or params.get("app_name") or params.get("path") or "").strip()
        if not app_name:
            return ToolResult(ok=False, error="Parâmetro 'app' ou 'name' é obrigatório.")

        # Se for um serviço web conhecido ou URL, abre via navegador
        web_services = {
            "spotify": "https://open.spotify.com",
            "youtube": "https://www.youtube.com",
            "github": "https://github.com",
            "gmail": "https://mail.google.com",
            "whatsapp": "https://web.whatsapp.com",
        }
        low_app = app_name.lower()
        if low_app in web_services or low_app.startswith(("http://", "https://", "www.")):
            return self.open_url({"url": web_services.get(low_app, app_name)})

        dispatched = False
        try:
            import time
            from tools.installed_apps import resolve_app, matching_windows
            app = resolve_app(app_name)
            self.control.check()
            existing = matching_windows(app.path)
            if existing:
                return ToolResult(True, f"{app.name} já está aberto.",
                    meta={"app": app.name, "executable": str(app.path), "windows": existing,
                          "verified": True, "check": "installed_app_window"})
            os.startfile(str(app.path))
            dispatched = True
            deadline = time.monotonic() + 4
            windows = []
            while time.monotonic() < deadline:
                self.control.check()
                windows = matching_windows(app.path)
                if windows:
                    break
                time.sleep(0.15)
            return ToolResult(True, f"{app.name}: " + ("janela confirmada." if windows else "abertura solicitada; janela ainda não confirmada."),
                meta={"app": app.name, "executable": str(app.path), "windows": windows,
                      "verified": bool(windows), "check": "installed_app_window"})
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao abrir '{app_name}': {exc}",
                              meta={"outcome_unknown": dispatched or getattr(exc, "outcome_unknown", False)})

    def list_installed_apps(self, params):
        from tools.installed_apps import installed_apps, normalized_name
        query = normalized_name(str(params.get("query") or params.get("app") or params.get("name") or params.get("app_name") or ""))
        apps = [{"name": app.name, "path": str(app.path), "source": app.source}
                for app in installed_apps() if not query or query in normalized_name(app.name)
                or query in normalized_name(app.path.stem)]
        total = len(apps)
        apps = apps[:30]
        # Keep executable paths in metadata; the planner can open by the observed name.
        summary = {"names": [app["name"] for app in apps], "total": total, "truncated": total > len(apps)}
        if not apps:
            summary["message"] = "Nenhum aplicativo instalado corresponde ao filtro."
        if not query or "steam" in query:
            summary["steam_games"] = "Use list_steam_games para consultar jogos instalados, não list_installed_apps."
        return ToolResult(True, json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                          meta={"apps": apps, "count": len(apps), "total": total})

    def list_steam_games(self, params):
        from tools.installed_apps import steam_game_catalog, normalized_name
        try:
            self.control.check()
            catalog = steam_game_catalog()
            query = normalized_name(str(params.get("query") or ""))
            games = [game for game in catalog.pop("games") if not query or query in normalized_name(game["name"])]
            limit, offset = params.get("limit", 20), params.get("offset", 0)
            if type(limit) is not int or not 1 <= limit <= 50 or type(offset) is not int or not 0 <= offset <= 512:
                return ToolResult(False, error="Use limit entre 1 e 50 e offset entre 0 e 512.")
            page = games[offset:offset + limit]
            result = {"games": page, "total": len(games), "offset": offset,
                      "next_offset": offset + len(page) if offset + len(page) < len(games) else None,
                      "note": "Manifestos locais; a lista pode incluir utilitários e não comprova que um jogo abre ou está licenciado.",
                      **catalog}
            return ToolResult(True, json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                              meta={"games": page, "count": len(page), "total": len(games), "check": "steam_local_manifests"})
        except (OSError, UnicodeError, ValueError) as exc:
            return ToolResult(False, error=f"Não foi possível consultar a biblioteca Steam: {exc}")

    def get_active_window(self, params: dict | None = None) -> ToolResult:
        """Retorna o título e detalhes da janela ativa em foco."""
        try:
            import pygetwindow as gw
            w = gw.getActiveWindow()
            if w and w.title:
                return ToolResult(
                    ok=True,
                    output=f"Janela ativa: '{w.title}'",
                    meta={"title": w.title, "x": w.left, "y": w.top, "width": w.width, "height": w.height},
                )
            return ToolResult(ok=True, output="Nenhuma janela ativa com foco detectada.", meta={})
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao obter janela ativa: {exc}")

    def mouse_move(self, params: dict) -> ToolResult:
        """Move o ponteiro do mouse suavemente para coordenadas (x, y)."""
        x = params.get("x")
        y = params.get("y")
        if x is None or y is None:
            return ToolResult(ok=False, error="Coordenadas 'x' e 'y' são obrigatórias.")
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.moveTo(int(x), int(y), duration=0.2)
            return ToolResult(ok=True, output=f"Mouse movido para ({x}, {y}).", meta={"x": x, "y": y})
        except Exception as exc:
            if "fail-safe" in str(exc).lower():
                return ToolResult(ok=False, error="Entrada interrompida pelo fail-safe do mouse.")
            return ToolResult(ok=False, error=f"Erro ao mover mouse: {exc}")

    def mouse_scroll(self, params: dict) -> ToolResult:
        """Rola a roda do mouse verticalmente (positivo para cima, negativo para baixo)."""
        clicks = int(params.get("clicks", params.get("amount", 2)))
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.scroll(clicks)
            return ToolResult(ok=True, output=f"Scroll de {clicks} unidades executado.", meta={"clicks": clicks})
        except Exception as exc:
            if "fail-safe" in str(exc).lower():
                return ToolResult(ok=False, error="Entrada interrompida pelo fail-safe do mouse.")
            return ToolResult(ok=False, error=f"Erro no scroll: {exc}")

    def mouse_drag(self, params: dict) -> ToolResult:
        """Arrasta o mouse de (x1, y1) até (x2, y2)."""
        x1 = params.get("x1", params.get("from_x"))
        y1 = params.get("y1", params.get("from_y"))
        x2 = params.get("x2", params.get("to_x"))
        y2 = params.get("y2", params.get("to_y"))
        duration = float(params.get("duration", 0.5))
        button = str(params.get("button", "left")).lower()

        if None in (x1, y1, x2, y2):
            return ToolResult(
                ok=False,
                error="Parâmetros 'x1', 'y1', 'x2', 'y2' são obrigatórios para mouse_drag.",
            )

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.moveTo(int(x1), int(y1))
            pyautogui.dragTo(int(x2), int(y2), duration=duration, button=button)
            return ToolResult(
                ok=True,
                output=f"Mouse arrastado de ({x1}, {y1}) até ({x2}, {y2}).",
                meta={"from": (x1, y1), "to": (x2, y2), "button": button},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao arrastar mouse: {exc}")

    def get_clipboard(self, params: dict | None = None) -> ToolResult:
        """Obtém o conteúdo textual da área de transferência (clipboard)."""
        try:
            import pyperclip

            content = pyperclip.paste()
            return ToolResult(
                ok=True,
                output=f"Conteúdo do clipboard ({len(content)} chars):\n{content}",
                meta={"text": content, "length": len(content)},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao ler clipboard: {exc}")

    def set_clipboard(self, params: dict) -> ToolResult:
        """Define o conteúdo da área de transferência (clipboard)."""
        text = str(params.get("text", params.get("content", "")))
        try:
            from tools.clipboard_io import copy_text

            copy_text(text)
            return ToolResult(
                ok=True,
                output=f"Texto copiado para a área de transferência ({len(text)} chars).",
                meta={"length": len(text)},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao escrever no clipboard: {exc}")

    def resize_window(self, params: dict) -> ToolResult:
        """Redimensiona uma janela especificada por título."""
        title = str(params.get("title", "")).strip().lower()
        width = params.get("width")
        height = params.get("height")
        if not title or width is None or height is None:
            return ToolResult(
                ok=False,
                error="Parâmetros 'title', 'width' e 'height' são obrigatórios.",
            )
        try:
            import pygetwindow as gw

            wins = [w for w in gw.getAllWindows() if title in w.title.lower() and w.title.strip()]
            if not wins:
                return ToolResult(ok=False, error=f"Janela '{title}' não encontrada.")
            if len(wins) != 1:
                return ToolResult(False, error="Título ambíguo; nenhuma janela foi alterada.")
            w = wins[0]
            self.control.check()
            w.resizeTo(int(width), int(height))
            return ToolResult(
                ok=True,
                output=f"Janela '{w.title}' redimensionada para {width}x{height}.",
                meta={"title": w.title, "width": width, "height": height},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao redimensionar janela: {exc}")

    def move_window(self, params: dict) -> ToolResult:
        """Move uma janela para coordenadas (x, y) na tela."""
        title = str(params.get("title", "")).strip().lower()
        x = params.get("x")
        y = params.get("y")
        if not title or x is None or y is None:
            return ToolResult(
                ok=False,
                error="Parâmetros 'title', 'x' e 'y' são obrigatórios.",
            )
        try:
            import pygetwindow as gw

            wins = [w for w in gw.getAllWindows() if title in w.title.lower() and w.title.strip()]
            if not wins:
                return ToolResult(ok=False, error=f"Janela '{title}' não encontrada.")
            if len(wins) != 1:
                return ToolResult(False, error="Título ambíguo; nenhuma janela foi alterada.")
            w = wins[0]
            self.control.check()
            w.moveTo(int(x), int(y))
            return ToolResult(
                ok=True,
                output=f"Janela '{w.title}' movida para ({x}, {y}).",
                meta={"title": w.title, "x": x, "y": y},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao mover janela: {exc}")

    def set_volume(self, params: dict) -> ToolResult:
        """Ajusta o volume de som do Windows (aumentar, diminuir ou definir)."""
        action = str(params.get("volume_action", params.get("mode", "up"))).lower()
        steps = int(params.get("steps", 5))
        if not 1 <= steps <= 50:
            return ToolResult(False, error="Volume aceita de 1 a 50 passos por chamada.")
        try:
            import pyautogui

            if "up" in action or "aumentar" in action:
                for _ in range(steps):
                    self.control.check()
                    pyautogui.press("volumeup")
                return ToolResult(ok=True, output=f"Volume aumentado em {steps} níveis.")
            elif "down" in action or "diminuir" in action:
                for _ in range(steps):
                    self.control.check()
                    pyautogui.press("volumedown")
                return ToolResult(ok=True, output=f"Volume diminuído em {steps} níveis.")
            elif "mute" in action or "mutar" in action:
                pyautogui.press("volumemute")
                return ToolResult(ok=True, output="Volume mutado/desmutado.")
            else:
                for _ in range(steps):
                    self.control.check()
                    pyautogui.press("volumeup")
                return ToolResult(ok=True, output=f"Volume ajustado ({action}).")
        except Exception as exc:
            if "fail-safe" in str(exc).lower():
                return ToolResult(ok=False, error="Entrada interrompida pelo fail-safe do mouse.")
            return ToolResult(ok=False, error=f"Erro ao ajustar volume: {exc}")

    def mute_volume(self, params: dict | None = None) -> ToolResult:
        """Ativa ou desativa o mudo do áudio do sistema."""
        try:
            import pyautogui

            pyautogui.press("volumemute")
            return ToolResult(ok=True, output="Áudio mutado/desmutado com sucesso.")
        except Exception as exc:
            if "fail-safe" in str(exc).lower():
                return ToolResult(ok=False, error="Entrada interrompida pelo fail-safe do mouse.")
            return ToolResult(ok=False, error=f"Erro ao alternar mudo: {exc}")

    def vision_locate_and_click(self, params: dict) -> ToolResult:
        """Localiza visualmente um elemento na tela via VLM e executa o clique com compensação de DPI."""
        target = str(params.get("target", params.get("description", ""))).strip()
        if not target:
            return ToolResult(ok=False, error="Parâmetro 'target' ou 'description' é obrigatório.")

        # 1. Captura screenshot da tela
        shot = self.take_screenshot(params)
        if not shot.ok or "path" not in shot.meta:
            return ToolResult(ok=False, error=f"Falha ao capturar screenshot: {shot.error}")

        img_path = shot.meta["path"]
        img_w = shot.meta.get("width", 1920)
        img_h = shot.meta.get("height", 1080)

        # 2. Chama VLM para detectar posição percentual ou coordenadas
        prompt = (
            f"Point to the center of the UI element '{target}'. "
            "Output ONLY the JSON format: {\"x_percent\": float, \"y_percent\": float} where values are 0.0 to 100.0."
        )

        try:
            import base64
            import re
            from core.runtime_budget import post_ollama_json

            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "model": "moondream:1.8b",
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
            }
            host = os.environ.get("NYX_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
            vlm_res = post_ollama_json(
                f"{host}/api/generate", payload, timeout=20.0
            ).get("response", "")

            # Tenta extrair coordenadas
            match = re.search(r"\{\s*\"x_percent\"\s*:\s*([0-9.]+)\s*,\s*\"y_percent\"\s*:\s*([0-9.]+)\s*\}", vlm_res)
            if match:
                xp = float(match.group(1)) / 100.0
                yp = float(match.group(2)) / 100.0
                if not (0 <= xp < 1 and 0 <= yp < 1):
                    return ToolResult(False, error="Coordenadas visuais fora da captura; nenhum clique foi feito.")
                cx = int(xp * img_w)
                cy = int(yp * img_h)
            else:
                return ToolResult(ok=False, error="Não há coordenadas verificáveis para o elemento; nenhum clique foi feito.")

            # MSS and UIA share physical pixels; preserve monitor/window origin.
            self.control.check()
            if shot.meta.get("coordinate_space") != "physical_pixels" or not shot.meta.get("hwnd"):
                return ToolResult(False, error="Selecione uma janela por hwnd/title antes de um clique visual.")
            from tools.windows_targets import physical_pixels, select_window
            with physical_pixels():
                window = select_window({"hwnd": shot.meta["hwnd"]})
                if (window.left, window.top, window.width, window.height) != (
                    shot.meta["left"], shot.meta["top"], img_w, img_h):
                    return ToolResult(False, error="A janela mudou desde a captura; inspecione novamente.")
            return self.click_coordinate({"hwnd": shot.meta["hwnd"],
                "x": shot.meta["left"] + cx, "y": shot.meta["top"] + cy})
        except Exception as exc:
            return ToolResult(
                ok=False,
                error=f"Falha na detecção visual de '{target}': {exc}",
            )

    def spawn_window(self, params: dict) -> ToolResult:
        """Cria e abre uma nova janela declarativa/generativa (HUD, gráfico, passos, etc)."""
        spec = params.get("spec", params)
        try:
            from ui.window_manager import WindowManager

            win_id = WindowManager.get_instance().spawn(spec)
            title = spec.get("title", "Janela Nyx")
            return ToolResult(
                ok=True,
                output=f"Janela generativa '{title}' criada com sucesso (ID: {win_id}).",
                meta={"window_id": win_id, "title": title},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao criar janela generativa: {exc}")

    def update_window(self, params: dict) -> ToolResult:
        """Atualiza componentes de uma janela generativa existente."""
        win_id = str(params.get("window_id", params.get("id", "")))
        patch = params.get("patch", params)
        if not win_id:
            return ToolResult(ok=False, error="Parâmetro 'window_id' ou 'id' é obrigatório.")
        try:
            from ui.window_manager import WindowManager

            ok = WindowManager.get_instance().update(win_id, patch)
            if ok:
                return ToolResult(
                    ok=True,
                    output=f"Janela '{win_id}' atualizada com sucesso.",
                    meta={"window_id": win_id},
                )
            return ToolResult(ok=False, error=f"Janela '{win_id}' não encontrada para atualização.")
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao atualizar janela: {exc}")

    def close_generative_window(self, params: dict) -> ToolResult:
        """Fecha uma janela generativa criada pela Nyx."""
        win_id = str(params.get("window_id", params.get("id", "")))
        if not win_id:
            return ToolResult(ok=False, error="Parâmetro 'window_id' ou 'id' é obrigatório.")
        try:
            from ui.window_manager import WindowManager

            ok = WindowManager.get_instance().close(win_id)
            if ok:
                return ToolResult(
                    ok=True,
                    output=f"Janela generativa '{win_id}' fechada com sucesso.",
                    meta={"window_id": win_id},
                )
            return ToolResult(ok=False, error=f"Janela '{win_id}' não encontrada.")
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao fechar janela generativa: {exc}")

    def list_generative_windows(self, params: dict | None = None) -> ToolResult:
        """Lista todas as janelas generativas ativas criadas pela Nyx."""
        try:
            from ui.window_manager import WindowManager

            wins = WindowManager.get_instance().list_windows()
            return ToolResult(
                ok=True,
                output=f"Janelas generativas ativas ({len(wins)}): {wins}",
                meta={"windows": wins, "count": len(wins)},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao listar janelas generativas: {exc}")

    def run(self, params: dict) -> ToolResult:
        """Despacha a ação de UI solicitada com base no subcampo 'action' ou no payload."""
        if self.control.is_cancelled():
            return ToolResult(False, error="Controle de interface interrompido.", meta={"blocked": True})
        action = params.get("action", params.get("ui_action", "list_windows"))
        dispatch = {
            "list_windows": self.list_windows,
            "focus_window": self.focus_window,
            "minimize_window": self.minimize_window,
            "maximize_window": self.maximize_window,
            "take_screenshot": self.take_screenshot,
            "screenshot": self.take_screenshot,
            "click": self.click_coordinate,
            "click_coordinate": self.click_coordinate,
            "move": self.mouse_move,
            "mouse_move": self.mouse_move,
            "scroll": self.mouse_scroll,
            "mouse_scroll": self.mouse_scroll,
            "type": self.type_text,
            "type_text": self.type_text,
            "press_key": self.press_key,
            "open_app": self.open_app,
            "list_installed_apps": self.list_installed_apps,
            "list_steam_games": self.list_steam_games,
            "launch": self.open_app,
            "open_url": self.open_url,
            "url": self.open_url,
            "browser": self.open_url,
            "active_window": self.get_active_window,
            "get_active_window": self.get_active_window,
            "inspect_elements": self.inspect_elements,
            "elements": self.inspect_elements,
            "screen_vision": self.screen_vision,
            "vision": self.screen_vision,
            "see_screen": self.screen_vision,
            "list_apps": self.list_running_apps,
            "list_running_apps": self.list_running_apps,
            "running_apps": self.list_running_apps,
            "apps": self.list_running_apps,
            "close_app": self.close_app,
            "close_window": self.close_app,
            "read_element": lambda p: self.element_action("read_element", p),
            "type_element": self.type_text,
            "click_element": self.click_element,
            "click_id": self.click_element,
            "kill_process": self.kill_process,
            "terminate_process": self.kill_process,
            "drag": self.mouse_drag,
            "mouse_drag": self.mouse_drag,
            "get_clipboard": self.get_clipboard,
            "read_clipboard": self.get_clipboard,
            "clipboard": self.get_clipboard,
            "set_clipboard": self.set_clipboard,
            "copy_clipboard": self.set_clipboard,
            "write_clipboard": self.set_clipboard,
            "resize_window": self.resize_window,
            "resize": self.resize_window,
            "move_window": self.move_window,
            "set_volume": self.set_volume,
            "volume": self.set_volume,
            "mute_volume": self.mute_volume,
            "mute": self.mute_volume,
            "vision_locate_and_click": self.vision_locate_and_click,
            "locate_and_click": self.vision_locate_and_click,
            "click_visual": self.vision_locate_and_click,
            "spawn_window": self.spawn_window,
            "ui_spawn": self.spawn_window,
            "create_window": self.spawn_window,
            "update_window": self.update_window,
            "ui_update": self.update_window,
            "close_generative_window": self.close_generative_window,
            "ui_close": self.close_generative_window,
            "list_generative_windows": self.list_generative_windows,
        }
        func = dispatch.get(action)
        if not func:
            return ToolResult(
                ok=False,
                error=(
                    f"Ação de UI desconhecida: '{action}'. "
                    f"Ações válidas: {list(dispatch.keys())}"
                ),
            )
        return func(params)


def make_ui_tool_func(tool: UITool):
    """Fábrica da função registrada como ação 'ui_action'."""

    def _run(params: dict) -> ToolResult:
        return tool.run(params)

    return _run
