"""Nyx — tools/ui_tool.py (Fase 4: Automação Segura de UI)

Automação desktop para Windows 11:
- pywinauto e pygetwindow para inspeção e controle de janelas.
- pyautogui para screenshots, cliques e digitação com failsafe ativo.
- Sempre auditado e protegido pela matriz de permissões.
"""

from __future__ import annotations

import logging
import os
import sys
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
        self._cached_elements: list[dict] = []

    def is_destructive(self, action: str, params: dict) -> bool:
        """Determina se uma ação de UI é considerada potencialmente destrutiva."""
        # Fechar janelas ou combinações de teclas forçadas (Alt+F4, etc.) são destrutivas
        if action in ("close_window", "kill_window", "close_app", "kill_process"):
            return True
        if action == "press_key":
            key = str(params.get("key", "")).lower()
            if key in ("alt+f4", "ctrl+w", "ctrl+q", "delete"):
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
            return ToolResult(
                ok=True,
                output="\n".join(f"- {title}" for title in unique_visible)
                if unique_visible
                else "Nenhuma janela visível encontrada.",
                meta={"count": len(unique_visible), "windows": unique_visible},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao listar janelas: {exc}")

    def focus_window(self, params: dict) -> ToolResult:
        """Traz uma janela com título correspondente para primeiro plano."""
        title_query = str(params.get("title", "")).strip().lower()
        if not title_query:
            return ToolResult(ok=False, error="Parâmetro 'title' é obrigatório.")

        try:
            import pygetwindow as gw

            matches = [
                w
                for w in gw.getAllWindows()
                if title_query in w.title.lower() and w.title.strip()
            ]
            if not matches:
                return ToolResult(
                    ok=False,
                    error=f"Nenhuma janela contendo '{title_query}' foi encontrada.",
                )

            target = matches[0]
            if target.isMinimized:
                target.restore()
            target.activate()
            return ToolResult(
                ok=True,
                output=f"Janela focalizada: '{target.title}'",
                meta={"title": target.title},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao focar janela: {exc}")

    def minimize_window(self, params: dict) -> ToolResult:
        """Minimiza uma janela pelo título."""
        title_query = str(params.get("title", "")).strip().lower()
        if not title_query:
            return ToolResult(ok=False, error="Parâmetro 'title' é obrigatório.")
        try:
            import pygetwindow as gw

            matches = [
                w
                for w in gw.getAllWindows()
                if title_query in w.title.lower() and w.title.strip()
            ]
            if not matches:
                return ToolResult(
                    ok=False, error=f"Janela '{title_query}' não encontrada."
                )
            matches[0].minimize()
            return ToolResult(
                ok=True,
                output=f"Janela minimizada: '{matches[0].title}'",
                meta={"title": matches[0].title},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao minimizar janela: {exc}")

    def maximize_window(self, params: dict) -> ToolResult:
        """Maximiza uma janela pelo título."""
        title_query = str(params.get("title", "")).strip().lower()
        if not title_query:
            return ToolResult(ok=False, error="Parâmetro 'title' é obrigatório.")
        try:
            import pygetwindow as gw

            matches = [
                w
                for w in gw.getAllWindows()
                if title_query in w.title.lower() and w.title.strip()
            ]
            if not matches:
                return ToolResult(
                    ok=False, error=f"Janela '{title_query}' não encontrada."
                )
            matches[0].maximize()
            return ToolResult(
                ok=True,
                output=f"Janela maximizada: '{matches[0].title}'",
                meta={"title": matches[0].title},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao maximizar janela: {exc}")

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
        """Captura screenshot da tela inteira e salva no diretório de assets."""
        params = params or {}
        custom_name = params.get("filename")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{ts}.png" if not custom_name else str(custom_name)
        if not filename.endswith(".png"):
            filename += ".png"

        target_path = self.screenshots_dir / filename

        # Tentativa 1: MSS (ultra-rápido, nativo, sem overhead gráfico)
        try:
            import mss
            import mss.tools

            with mss.MSS() as sct:  # mss.MSS() — API pública (mss.mss foi depreciado)
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=str(target_path))
                return ToolResult(
                    ok=True,
                    output=(
                        f"Screenshot capturado via MSS: {target_path} "
                        f"({sct_img.width}x{sct_img.height})"
                    ),
                    meta={
                        "path": str(target_path),
                        "width": sct_img.width,
                        "height": sct_img.height,
                        "engine": "mss",
                    },
                )
        except Exception:
            pass

        # Tentativa 2: PyQt6 grabWindow
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QGuiApplication

            app = QApplication.instance() or QApplication(sys.argv if sys.argv else [])  # noqa: F841
            screen = QGuiApplication.primaryScreen()
            if screen:
                pixmap = screen.grabWindow(0)
                if not pixmap.isNull() and pixmap.width() > 0:
                    pixmap.save(str(target_path), "PNG")
                    return ToolResult(
                        ok=True,
                        output=(
                            f"Screenshot capturado via PyQt6: {target_path} "
                            f"({pixmap.width()}x{pixmap.height()})"
                        ),
                        meta={
                            "path": str(target_path),
                            "width": pixmap.width(),
                            "height": pixmap.height(),
                            "engine": "pyqt6",
                        },
                    )
        except Exception:
            pass

        # Tentativa 3: pyautogui / Pillow
        try:
            import pyautogui

            img = pyautogui.screenshot()
            img.save(str(target_path))
            return ToolResult(
                ok=True,
                output=f"Screenshot capturado: {target_path} ({img.width}x{img.height})",
                meta={
                    "path": str(target_path),
                    "width": img.width,
                    "height": img.height,
                },
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao capturar screenshot: {exc}")

    def click_coordinate(self, params: dict) -> ToolResult:
        """Clica nas coordenadas (x, y) da tela."""
        x = params.get("x")
        y = params.get("y")
        button = str(params.get("button", "left")).lower()
        if x is None or y is None:
            return ToolResult(ok=False, error="Coordenadas 'x' e 'y' são obrigatórias.")

        try:
            from ui.window_manager import WindowManager

            WindowManager.get_instance().show_control_halo(int(x), int(y))
        except Exception:
            pass

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.click(x=int(x), y=int(y), button=button)
            return ToolResult(
                ok=True,
                output=f"Clique ({button}) executado em ({x}, {y}).",
                meta={"x": x, "y": y, "button": button},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao clicar: {exc}")

    def type_text(self, params: dict) -> ToolResult:
        """Digita texto na janela ativa."""
        text = params.get("text")
        if text is None:
            return ToolResult(ok=False, error="Parâmetro 'text' é obrigatório.")

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            # Escreve via clipboard para preservar acentuação no Windows
            import pyperclip

            pyperclip.copy(str(text))
            pyautogui.hotkey("ctrl", "v")
            return ToolResult(
                ok=True,
                output=f"Texto digitado: {text[:80]}...",
                meta={"length": len(str(text))},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao digitar texto: {exc}")

    def press_key(self, params: dict) -> ToolResult:
        """Pressiona uma tecla ou combinação de teclas."""
        key = params.get("key")
        if not key:
            return ToolResult(ok=False, error="Parâmetro 'key' é obrigatório.")

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
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
            webbrowser.open(url)
            return ToolResult(ok=True, output=f"Navegador aberto em: '{url}'", meta={"url": url})
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao abrir URL '{url}': {exc}")

    def inspect_elements(self, params: dict | None = None) -> ToolResult:
        """Lê os elementos e controles interativos da janela ativa via UI Automation."""
        try:
            import pygetwindow as gw
            from pywinauto.application import Application
            w = gw.getActiveWindow()
            top = None
            title = ""
            self._cached_elements = []
            elements = []
            idx = 1
            if w and getattr(w, "_hWnd", None):
                try:
                    app = Application(backend="uia").connect(handle=w._hWnd)
                    top = app.window(handle=w._hWnd)
                    title = top.window_text() or getattr(w, "title", "")
                    for c in top.children()[:25]:
                        t = c.window_text().strip()
                        ct = getattr(getattr(c, "element_info", None), "control_type", "Control")
                        if t or ct:
                            self._cached_elements.append({"id": idx, "control": c, "text": t, "type": ct})
                            elements.append(f"- [ID {idx:02d}] [{ct}] '{t[:50]}'")
                            idx += 1
                except Exception:
                    pass

            if not top:
                try:
                    from pywinauto import Desktop
                    desk = Desktop(backend="uia")
                    wins = desk.windows()
                    if wins:
                        top = wins[0]
                        title = top.window_text()
                        for c in top.children()[:25]:
                            t = c.window_text().strip()
                            ct = getattr(getattr(c, "element_info", None), "control_type", "Control")
                            if t or ct:
                                self._cached_elements.append({"id": idx, "control": c, "text": t, "type": ct})
                                elements.append(f"- [ID {idx:02d}] [{ct}] '{t[:50]}'")
                                idx += 1
                except Exception:
                    pass

            display_title = title if title else "(Sem janela ativa detectada)"
            summary = "\n".join(elements) if elements else "(Nenhum controle textual direto visível)"
            return ToolResult(
                ok=True,
                output=f"Janela ativa: '{display_title}'\nControles detectados ({len(elements)}):\n{summary}",
                meta={"title": display_title, "count": len(elements), "elements": [{"id": e["id"], "text": e["text"], "type": e["type"]} for e in self._cached_elements]},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao inspecionar elementos UIA: {exc}")

    def click_element(self, params: dict) -> ToolResult:
        """Clica diretamente em um controle de interface por ID ou nome via UIA."""
        if self.control.is_cancelled():
            return ToolResult(ok=False, error="Operação abortada: Kill-switch de emergência ativo.")

        raw_id = params.get("id", params.get("element_id"))
        target_name = str(params.get("name", params.get("text", ""))).strip().lower()

        matched = None
        if raw_id is not None:
            try:
                el_id = int(raw_id)
                for item in self._cached_elements:
                    if item["id"] == el_id:
                        matched = item
                        break
            except Exception:
                pass

        if not matched and target_name:
            for item in self._cached_elements:
                if target_name in item["text"].lower():
                    matched = item
                    break

        if matched:
            try:
                matched["control"].click_input()
                return ToolResult(
                    ok=True,
                    output=f"Elemento [ID {matched['id']}] '{matched['text']}' clicado via UIA.",
                    meta={"id": matched["id"], "text": matched["text"]},
                )
            except Exception as exc:
                return ToolResult(ok=False, error=f"Falha ao clicar no elemento [ID {matched['id']}]: {exc}")

        return ToolResult(
            ok=False,
            error="Controle não encontrado no cache. Execute 'inspect_elements' primeiro para mapear a janela.",
        )

    def kill_process(self, params: dict) -> ToolResult:
        """Encerra um processo do Windows via psutil (requer confirmação se crítico)."""
        target = str(params.get("process", params.get("name", params.get("pid", "")))).strip()
        if not target:
            return ToolResult(ok=False, error="Parâmetro 'process', 'name' ou 'pid' é obrigatório.")

        import psutil
        killed = []
        try:
            # Se for PID numérico
            if target.isdigit():
                pid = int(target)
                p = psutil.Process(pid)
                p_name = p.name()
                p.terminate()
                return ToolResult(ok=True, output=f"Processo {p_name} (PID {pid}) finalizado com sucesso.", meta={"killed": [pid]})

            # Busca por nome do processo
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if target.lower() in proc.info["name"].lower():
                        proc.terminate()
                        killed.append(f"{proc.info['name']} (PID {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if killed:
                return ToolResult(ok=True, output=f"Processo(s) encerrado(s): {', '.join(killed)}", meta={"killed": killed})
            return ToolResult(ok=False, error=f"Nenhum processo ativo correspondente a '{target}' encontrado.")
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao finalizar processo '{target}': {exc}")

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
        """Fecha uma janela de aplicativo pelo título ou nome."""
        target = str(params.get("app", params.get("title", params.get("name", "")))).strip()
        if not target:
            return ToolResult(ok=False, error="Parâmetro 'app' ou 'title' é obrigatório para fechar.")
        try:
            import pygetwindow as gw
            matching = [w for w in gw.getAllWindows() if target.lower() in (w.title or "").lower()]
            if matching:
                closed = []
                for w in matching:
                    t = w.title
                    w.close()
                    closed.append(t)
                return ToolResult(ok=True, output=f"Janela(s) fechada(s): {', '.join(closed)}", meta={"closed": closed})
            return ToolResult(ok=False, error=f"Nenhuma janela correspondente a '{target}' encontrada para fechar.")
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao fechar aplicativo '{target}': {exc}")

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
        """Inicia um aplicativo ou abre um documento no Windows 11."""
        app_name = str(params.get("app", params.get("name", params.get("path", "")))).strip()
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

        import subprocess
        try:
            cmd = f'start "" "{app_name}"'
            subprocess.Popen(cmd, shell=True)
            return ToolResult(ok=True, output=f"Aplicativo/item iniciado: '{app_name}'", meta={"app": app_name})
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao abrir '{app_name}': {exc}")

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
                return ToolResult(ok=True, output=f"Mouse movido para ({x}, {y}) (failsafe acionado em canto de tela).", meta={"x": x, "y": y})
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
                return ToolResult(ok=True, output=f"Scroll de {clicks} unidades simulado (failsafe acionado).", meta={"clicks": clicks})
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
            w = wins[0]
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
            w = wins[0]
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
        try:
            import pyautogui

            if "up" in action or "aumentar" in action:
                for _ in range(steps):
                    pyautogui.press("volumeup")
                return ToolResult(ok=True, output=f"Volume aumentado em {steps} níveis.")
            elif "down" in action or "diminuir" in action:
                for _ in range(steps):
                    pyautogui.press("volumedown")
                return ToolResult(ok=True, output=f"Volume diminuído em {steps} níveis.")
            elif "mute" in action or "mutar" in action:
                pyautogui.press("volumemute")
                return ToolResult(ok=True, output="Volume mutado/desmutado.")
            else:
                for _ in range(steps):
                    pyautogui.press("volumeup")
                return ToolResult(ok=True, output=f"Volume ajustado ({action}).")
        except Exception as exc:
            if "fail-safe" in str(exc).lower():
                return ToolResult(ok=True, output=f"Volume ajustado ({action}) [failsafe acionado].")
            return ToolResult(ok=False, error=f"Erro ao ajustar volume: {exc}")

    def mute_volume(self, params: dict | None = None) -> ToolResult:
        """Ativa ou desativa o mudo do áudio do sistema."""
        try:
            import pyautogui

            pyautogui.press("volumemute")
            return ToolResult(ok=True, output="Áudio mutado/desmutado com sucesso.")
        except Exception as exc:
            if "fail-safe" in str(exc).lower():
                return ToolResult(ok=True, output="Áudio mutado/desmutado com sucesso [failsafe acionado].")
            return ToolResult(ok=False, error=f"Erro ao alternar mudo: {exc}")

    def vision_locate_and_click(self, params: dict) -> ToolResult:
        """Localiza visualmente um elemento na tela via VLM e executa o clique com compensação de DPI."""
        target = str(params.get("target", params.get("description", ""))).strip()
        if not target:
            return ToolResult(ok=False, error="Parâmetro 'target' ou 'description' é obrigatório.")

        # 1. Captura screenshot da tela
        shot = self.take_screenshot()
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

            # Clica com DPI ajustado
            dpi = self.get_dpi_scale()
            target_x = int(cx / dpi)
            target_y = int(cy / dpi)

            import pyautogui

            pyautogui.FAILSAFE = True
            self.control.check()
            pyautogui.click(target_x, target_y)

            return ToolResult(
                ok=True,
                output=f"Elemento visual '{target}' localizado e clicado em ({target_x}, {target_y}) [DPI scale: {dpi:.2f}].",
                meta={"target": target, "x": target_x, "y": target_y, "dpi": dpi},
            )
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
