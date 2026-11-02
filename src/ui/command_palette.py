"""Keyboard-first command palette for the Nyx desktop shell."""

from __future__ import annotations

from typing import Callable, Iterable
from difflib import SequenceMatcher
import unicodedata

from PyQt6.QtCore import QEvent, Qt
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
        self.input.setAccessibleName('Buscar comando, conversa ou configuração')
        self.input.installEventFilter(self)
        layout.addWidget(self.input)

        self.list = QListWidget(panel)
        self.list.setObjectName("PaletteList")
        self.list.setAccessibleName('Comandos encontrados')
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
        def normalized(value):
            return unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().casefold()
        query = normalized(text.strip())
        self.list.clear()
        ranked = []
        for order,(title,hint,callback) in enumerate(self._commands):
            name = normalized(title+' '+hint)
            score = 1 if not query or query in name else max(
                (SequenceMatcher(None,query,word).ratio() for word in name.split()),default=0)
            if query and score < .6:
                continue
            ranked.append((-score,order,title,hint,callback))
        for _,_,title,hint,callback in sorted(ranked):
            item = QListWidgetItem(f"{title}    {hint}" if hint else title)
            item.setToolTip(title+' '+hint)
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

    def eventFilter(self, watched, event):
        if watched is self.input and event.type()==QEvent.Type.KeyPress and event.key() in {Qt.Key.Key_Down,Qt.Key.Key_Up}:
            if self.list.count():
                direction = 1 if event.key()==Qt.Key.Key_Down else -1
                self.list.setCurrentRow((self.list.currentRow()+direction)%self.list.count())
            return True
        return super().eventFilter(watched,event)

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        callback = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        callback()
