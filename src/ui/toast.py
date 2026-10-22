"""Transient in-window notifications, replacing dialogs for small feedback."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel


class Toast(QFrame):
    """A floating message that fades in, waits, and fades out."""

    DEFAULT_TIMEOUT_MS = 2600

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self.label = QLabel(self)
        self.label.setObjectName("ToastText")
        layout.addWidget(self.label)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_toast)
        self.hide()

    def show_message(self, text: str, timeout_ms: int | None = None) -> None:
        self.label.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._animate(1.0, 150)
        self._timer.start(timeout_ms or self.DEFAULT_TIMEOUT_MS)

    def hide_toast(self) -> None:
        self._timer.stop()
        self._animate(0.0, 180)
        QTimer.singleShot(200, self.hide)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = max(12, (parent.width() - self.width()) // 2)
        y = max(12, parent.height() - self.height() - 34)
        self.move(x, y)

    def _animate(self, target: float, duration_ms: int) -> None:
        self._animation.stop()
        self._animation.setDuration(duration_ms)
        self._animation.setStartValue(self._effect.opacity())
        self._animation.setEndValue(target)
        self._animation.start()
