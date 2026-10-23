"""Window identity and expiring UIA snapshots for targeted Windows actions."""
from collections import deque
from contextlib import contextmanager
import ctypes
import os
import time
from uuid import uuid4


@contextmanager
def physical_pixels():
    """UIA and MSS use physical pixels; do not divide them by system DPI."""
    previous = None
    setter = None
    if os.name == "nt":
        setter = ctypes.windll.user32.SetThreadDpiAwarenessContext
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = ctypes.c_void_p
        previous = setter(ctypes.c_void_p(-4))  # per-monitor v2, restored below
        if not previous:
            raise RuntimeError("Não foi possível definir coordenadas físicas nesta thread.")
    try:
        yield
    finally:
        if setter and previous:
            setter(previous)


def select_window(params, *, allow_active=False):
    import pygetwindow as gw
    hwnd = params.get("hwnd")
    title = str(params.get("title") or "").strip().casefold()
    if hwnd is not None:
        matches = [w for w in gw.getAllWindows() if w._hWnd == int(hwnd)]
        if title:
            matches = [w for w in matches if title in w.title.casefold()]
    elif title:
        matches = [w for w in gw.getAllWindows() if title in (w.title or "").casefold()]
    elif allow_active:
        active = gw.getActiveWindow()
        matches = [active] if active else []
    else:
        raise ValueError("Informe 'hwnd' ou 'title' da janela; um alvo explícito é obrigatório.")
    if len(matches) != 1:
        raise ValueError("Janela não encontrada." if not matches else
                         "Título ambíguo: mais de uma janela. Escolha o hwnd retornado por list_windows.")
    return matches[0]


def window_identity(window):
    import psutil
    import win32process
    _, pid = win32process.GetWindowThreadProcessId(window._hWnd)
    return (window._hWnd, pid, psutil.Process(pid).create_time())


@contextmanager
def uia_context():
    initialized = False
    if os.name == "nt":
        result = ctypes.windll.ole32.CoInitializeEx(None, 0)
        initialized = result in (0, 1)
        if not initialized and result != -2147417850:  # existing STA is valid too
            raise RuntimeError("Não foi possível iniciar UI Automation nesta thread.")
    try:
        with physical_pixels():
            yield
    finally:
        if initialized:
            ctypes.windll.ole32.CoUninitialize()


def focus(window, control):
    import pygetwindow as gw
    import win32gui
    control.check()
    if not win32gui.IsWindowEnabled(window._hWnd):
        raise ValueError("Janela bloqueada por diálogo modal; selecione o diálogo primeiro.")
    if window.isMinimized:
        window.restore()
    if not window.isActive:
        try:
            window.activate()
        except Exception:
            # pygetwindow can raise error code 0 even when focus changes.
            # Only the subsequent observed HWND decides success.
            pass
    if not window.isActive:
        from pywinauto import Desktop
        Desktop(backend="uia").window(handle=window._hWnd).wrapper_object().set_focus()
    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline:
        control.check()
        active = gw.getActiveWindow()
        if active and active._hWnd == window._hWnd:
            return
        time.sleep(0.04)
    raise ValueError("A janela não recebeu foco; confira janelas modais antes de continuar.")


class UIATargets:
    def __init__(self, control, clock=time.monotonic):
        self.control = control
        self.clock = clock
        self.snapshot = None
        self.elements = []
        self.identity = None
        self.created = 0
        self.mutation_started = False

    def inspect(self, params):
        with uia_context():
            return self._inspect(params)

    def _walk(self, top):
        queue = deque((child, 1) for child in top.children()[:80])
        started = self.clock()
        visited = 0
        while queue and visited < 80 and self.clock() - started < 3:
            self.control.check()
            item, depth = queue.popleft()
            visited += 1
            yield item
            if depth < 4:
                try:
                    queue.extend((child, depth + 1) for child in item.children()[:40])
                except Exception:
                    continue

    def _inspect(self, params):
        from pywinauto import Desktop
        self.snapshot = None
        self.elements = []
        window = select_window(params, allow_active=True)
        self.identity = window_identity(window)
        top = Desktop(backend="uia").window(handle=window._hWnd).wrapper_object()
        self.created = self.clock()
        errors = []
        invisible = 0
        for item in self._walk(top):
            try:
                if not item.is_visible():
                    invisible += 1
                    continue
                info = item.element_info
                password = bool(info.element.CurrentIsPassword)
                name = "[campo protegido]" if password else str(info.name or "")[:160]
                rect = item.rectangle()
                self.elements.append({"id": len(self.elements) + 1,
                    "runtime_id": tuple(info.runtime_id), "name": name,
                    "rect": [rect.left, rect.top, rect.right, rect.bottom],
                    "type": info.control_type, "password": password})
            except Exception as exc:
                if len(errors) < 2:
                    errors.append(str(exc)[:300])
                continue
        if not self.elements and errors:
            raise RuntimeError("Controles UIA indisponíveis: " + "; ".join(errors))
        self.snapshot = uuid4().hex
        return {"snapshot": self.snapshot, "hwnd": window._hWnd, "title": window.title,
                "window_rect": [window.left, window.top, window.width, window.height],
                "invisible_controls": invisible,
                "expires_seconds": 30, "scope": "Até 80 controles, quatro níveis e três segundos entre chamadas UIA.", "elements": [
                    {k: e[k] for k in ("id", "name", "type", "password", "rect")} for e in self.elements]}

    def resolve(self, params):
        self.control.check()
        if not self.snapshot or params.get("snapshot") != self.snapshot or self.clock() - self.created > 30:
            raise ValueError("Inspeção ausente ou antiga. Execute inspect_elements e use seu snapshot atual.")
        window = select_window({"hwnd": self.identity[0]})
        if window_identity(window) != self.identity:
            raise ValueError("A identidade da janela mudou. Inspecione novamente.")
        if params.get("id") is not None:
            matches = [e for e in self.elements if e["id"] == int(params["id"])]
        else:
            name = str(params.get("name") or "").strip()
            matches = [e for e in self.elements if name and e["name"] == name]
        if len(matches) != 1:
            raise ValueError("Controle não encontrado ou nome ambíguo; escolha um ID da inspeção atual.")
        entry = matches[0]
        from pywinauto import Desktop
        top = Desktop(backend="uia").window(handle=window._hWnd).wrapper_object()
        element = next((item for item in self._walk(top)
                        if tuple(item.element_info.runtime_id) == entry["runtime_id"]), None)
        if element is None:
            raise ValueError("O controle não está mais na janela. Inspecione novamente.")
        if entry["password"] or element.element_info.element.CurrentIsPassword:
            raise ValueError("Campo protegido: use entrada humana diretamente no aplicativo.")
        if (tuple(element.element_info.runtime_id) != entry["runtime_id"] or
            element.element_info.process_id != self.identity[1]):
            raise ValueError("O controle mudou de identidade; inspecione novamente.")
        if not element.is_visible() or not element.is_enabled():
            raise ValueError("Controle invisível ou desabilitado; nenhuma entrada realizada.")
        return window, element

    def act(self, action, params):
        self.mutation_started = False
        with uia_context():
            window, element = self.resolve(params)
            if action == "read_element":
                value = self._text(element)
                return {"text": value[:2000], "truncated": len(value) > 2000, "verified": True}
            focus(window, self.control)
            self.control.check()
            import win32gui
            if not win32gui.IsWindowEnabled(window._hWnd):
                raise ValueError("Janela bloqueada por diálogo modal; nenhuma entrada realizada.")
            if action == "type_element":
                text = params.get("text")
                if not isinstance(text, str) or len(text) > 2000:
                    raise ValueError("Informe texto com no máximo 2000 caracteres.")
                if element.element_info.control_type != "Edit":
                    raise ValueError("Alvo não é um campo de edição.")
                self.mutation_started = True
                element.set_edit_text(text)
                verified = self._text(element) == text
                return {"verified": verified, "check": "field_value", "length": len(text)}
            if action == "click_element":
                # Invoke addresses the identified UIA element without guessed coordinates.
                self.mutation_started = True
                element.invoke()
                return {"verified": False, "check": "dispatch_only", "dispatched": True,
                        "message": "Controle acionado. Leia a pós-condição antes de declarar conclusão."}
            raise ValueError("Ação UIA desconhecida.")

    @staticmethod
    def _text(element):
        if element.element_info.control_type == "Edit":
            return str(element.get_value())
        return str(element.window_text())
