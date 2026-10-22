"""Keyboard-first command palette for the Nyx desktop shell."""

from __future__ import annotations

from typing import Callable, Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

Command = tuple[str, str, Callable[[], None]]


class CommandPalette(QDialog):
    """A small, searchable list of actions; Enter runs, Esc closes."""

    MAX_VISIBLE = 9

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setObjectName("QuickPalette")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame(self)
        panel.setObjectName("PalettePanel")
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        self._panel_layout = layout

        self.input = QLineEdit(panel)
        self.input.setObjectName("PaletteInput")
        self.input.setPlaceholderText("Digite um comando ou o nome de uma conversa…")
        self.input.setClearButtonEnabled(True)
        layout.addWidget(self.input)

        self.list = QListWidget(panel)
        self.list.setObjectName("PaletteList")
        self.list.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.list)

        self.hint = QLabel("Enter executa · Esc fecha · ↑ ↓ navegam", panel)
        self.hint.setObjectName("Muted")
        layout.addWidget(self.hint)

        self._commands: list[Command] = []
        self.input.textChanged.connect(self._refresh)
        self.input.returnPressed.connect(self._run_current)
        self.list.itemClicked.connect(lambda _item: self._run_current())
        self.setMinimumWidth(520)

    # -- public API --------------------------------------------------------
    def set_commands(self, commands: Iterable[Command]) -> None:
        self._commands = [command for command in commands if len(command) == 3]
        self._refresh(self.input.text())

    @property
    def visible_commands(self) -> list[str]:
        return [self.list.item(row).text() for row in range(self.list.count())]

    def open_with(self, text: str = "") -> None:
        self.input.blockSignals(True)
        self.input.setText(text)
        self.input.blockSignals(False)
        self._refresh(text)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.input.selectAll()

    def focus_in_parent(self) -> None:
        """Center the dialog over its parent window."""
        if (parent := self.parentWidget()) is not None:
            centre = parent.frameGeometry().center()
            self.adjustSize()
            self.move(centre.x() - self.width() // 2, centre.y() - self.height() // 3)

    # -- internals ---------------------------------------------------------
    def _refresh(self, text: str) -> None:
        query = text.strip().casefold()
        self.list.clear()
        for title, hint, callback in self._commands:
            if query and query not in title.casefold() and query not in hint.casefold():
                continue
            item = QListWidgetItem(f"{title}    {hint}" if hint else title)
            item.setData(Qt.ItemDataRole.UserRole, callback)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
            rows = min(self.list.count(), self.MAX_VISIBLE)
            heights = [self.list.sizeHintForRow(row) for row in range(rows)]
            self.list.setFixedHeight(sum(height for height in heights if height > 0) + 8)
        else:
            self.list.setFixedHeight(56)
        if self.isVisible():
            self.adjustSize()
        margins = self._panel_layout.contentsMargins()
        self.setFixedHeight(
            margins.top()
            + margins.bottom()
            + self.input.sizeHint().height()
            + self.list.height()
            + self.hint.sizeHint().height()
            + self._panel_layout.spacing() * 2
        )

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        callback = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        callback()
