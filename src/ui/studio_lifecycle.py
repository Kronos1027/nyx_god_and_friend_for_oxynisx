"""Keep Qt alive until owned studio workers finish during application shutdown."""

import weakref

from PyQt6.QtCore import QObject, QEvent, QTimer
from PyQt6.QtWidgets import QApplication


class StudioLifecycle(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.windows = weakref.WeakSet()
        self.stopping = False
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.check_finished)
        app.installEventFilter(self)

    @classmethod
    def register(cls, window):
        app = QApplication.instance()
        lifecycle = getattr(app, "_nyx_studio_lifecycle", None)
        if lifecycle is None:
            lifecycle = cls(app)
            app._nyx_studio_lifecycle = lifecycle
        lifecycle.windows.add(window)

    def busy_windows(self):
        return [window for window in self.windows
                if any(panel.job is not None for panel in window.background_panels) or window.telemetry_job is not None]

    def eventFilter(self, watched, event):
        if watched is self.app and event.type() == QEvent.Type.Quit:
            self.stopping = True
            busy = self.busy_windows()
            for window in busy:
                window.setEnabled(False)
                for panel in window.background_panels:
                    panel.cancelled.set()
                window.lbl_status.setText("Encerrando: aguardando operações do Estúdio…")
            if busy:
                self.timer.start()
                return True
        return super().eventFilter(watched, event)

    def check_finished(self):
        if not self.busy_windows():
            self.timer.stop()
            self.app.quit()
