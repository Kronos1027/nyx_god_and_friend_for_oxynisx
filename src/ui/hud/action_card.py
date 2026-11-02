"""Plain-text action receipts with separate opening and focus observations."""
import json
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QToolButton, QPlainTextEdit


class ActionCard(QFrame):
    def __init__(self, progress, observation=None, parent=None):
        super().__init__(parent)
        self.setObjectName('HudActionCard')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14,10,14,10)
        observation = observation or {}
        params = observation.get('params',{})
        opened = params.get('action') in {'open_app','launch'}
        verified = bool(progress.get('verified'))
        title = QLabel(('ABRIR APP' if opened else str(progress.get('tool','AÇÃO')).upper())+f" · etapa {progress.get('step','')}")
        title.setObjectName('HudData')
        layout.addWidget(title)
        state = QLabel(('Janela confirmada' if opened else 'Etapa verificada') if verified else
                       'Resultado não verificado' if progress.get('ok') else 'A ação falhou')
        state.setObjectName('ActionState')
        state.setProperty('verified',verified)
        layout.addWidget(state)
        focus = progress.get('focus_verified', observation.get('focus_verified',observation.get('foreground_verified')))
        if opened and focus is not None:
            label = QLabel('Foco confirmado' if focus else 'Aberto, mas não foi possível trazer para frente')
            label.setWordWrap(True)
            label.setObjectName('Muted')
            layout.addWidget(label)
        self.toggle = QToolButton()
        self.toggle.setText('Ver detalhes')
        self.toggle.setCheckable(True)
        self.toggle.setAccessibleName('Expandir detalhes da ação')
        layout.addWidget(self.toggle)
        self.details = QPlainTextEdit()
        self.details.setObjectName('HudTrace')
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(180)
        self.details.setPlainText(json.dumps(observation or progress,ensure_ascii=False,indent=2))
        self.details.hide()
        self.toggle.toggled.connect(self.details.setVisible)
        layout.addWidget(self.details)
        for label in self.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)

