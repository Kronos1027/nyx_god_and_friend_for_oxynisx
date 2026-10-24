"""Bounded delivery to Qt's GUI thread with acknowledgement and no late replay."""

from dataclasses import dataclass, field
import threading
import time

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication

from tools.registry import ToolResult


@dataclass
class DisplayRequest:
    payload: dict
    cancelled: object
    deadline: float
    done: threading.Event = field(default_factory=threading.Event)
    lock: object = field(default_factory=threading.Lock)
    started: bool = False
    abandoned: bool = False
    result: ToolResult | None = None


class WorkspaceDispatcher(QObject):
    requested = pyqtSignal(object)

    def __init__(self, app):
        if QThread.currentThread() != app.thread():
            raise RuntimeError("O despachante do Estúdio deve ser criado na thread da interface.")
        super().__init__(app)
        self.pending = None
        self.lock = threading.Lock()
        self.requested.connect(self.deliver, Qt.ConnectionType.QueuedConnection)

    @classmethod
    def for_application(cls):
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return None
        dispatcher = getattr(app, "_nyx_workspace_dispatcher", None)
        if dispatcher is None and QThread.currentThread() == app.thread():
            dispatcher = cls(app)
            app._nyx_workspace_dispatcher = dispatcher
        return dispatcher

    def submit(self, payload, cancelled, timeout):
        if self.shutting_down():
            return ToolResult(False, error="A interface está encerrando; exibição recusada.")
        request = DisplayRequest(payload, cancelled, time.monotonic() + timeout)
        with self.lock:
            if self.pending is not None:
                return ToolResult(False, error="O Estúdio ainda está processando outra exibição.")
            self.pending = request
        if QThread.currentThread() == self.thread():
            self.deliver(request)
        else:
            self.requested.emit(request)
        while not request.done.wait(0.02):
            if cancelled() or time.monotonic() >= request.deadline:
                with request.lock:
                    if request.result is not None:
                        return request.result
                    request.abandoned = True
                    return ToolResult(
                        False,
                        error="Exibição cancelada ou sem confirmação da interface no prazo.",
                        meta={"outcome_unknown": request.started},
                    )
        return request.result

    @pyqtSlot(object)
    def deliver(self, request):
        try:
            with request.lock:
                if request.abandoned or request.cancelled() or self.shutting_down() or time.monotonic() >= request.deadline:
                    request.result = ToolResult(False, error="Exibição descartada antes de abrir a janela.")
                    return
                request.started = True
            result = self.display(request.payload)
            with request.lock:
                request.result = result
        except Exception as error:
            with request.lock:
                request.result = ToolResult(
                    False, error=f"Não foi possível exibir o Estúdio: {error}",
                    meta={"outcome_unknown": request.started},
                )
        finally:
            with self.lock:
                if self.pending is request:
                    self.pending = None
            request.done.set()

    @staticmethod
    def shutting_down():
        app = QApplication.instance()
        lifecycle = getattr(app, "_nyx_studio_lifecycle", None)
        return app is None or app.closingDown() or bool(lifecycle and lifecycle.stopping)

    @staticmethod
    def display(payload):
        from ui.workspace_window import WorkspaceWindow

        window = WorkspaceWindow.get_instance()
        view, title = payload["view"], payload["title"]
        if view == "code":
            window.display_code(payload["content"], title=title, language=payload["language"])
        elif view == "sheet":
            window.display_table(payload["content"], headers=payload["headers"], title=title)
        elif view == "doc":
            window.display_document(payload["content"], title=title)
        else:
            window.refresh_telemetry()
            window.tabs.setCurrentIndex(3)
            window.show()
        if not window.isVisible():
            return ToolResult(False, error="A janela do Estúdio não ficou visível.")
        return ToolResult(
            True, output=f"Janela de trabalho '{view}' exibida com sucesso: {title}"
            + (". Consulta de telemetria em andamento; resultado ainda não confirmado." if view == "telemetry" else ""),
            meta={"view": view, "title": title, "displayed": True,
                  "telemetry_pending": view == "telemetry"},
        )
