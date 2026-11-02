"""One explicit review of an immutable pending action; no ambient approvals."""
import copy
import json
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QSizePolicy, QLayout


class ConfirmCard(QFrame):
    decided = pyqtSignal(bool)
    edit_requested = pyqtSignal()

    def __init__(self, pending_action, prompt=None, is_destructive=False, parent=None):
        super().__init__(parent)
        self.pending_action = copy.deepcopy(pending_action)
        self.is_destructive = is_destructive
        self.resolved = False
        self.setObjectName('ConfirmCard')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setProperty('destructive',is_destructive)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(16,14,16,14)
        action = self.pending_action.get('params',{}).get('action')
        low_impact = self.pending_action.get('type')=='ui_action' and action in {
            'open_app','focus_window','open_url','scroll','list_windows','minimize_window','maximize_window'}
        # Display only. Existing registry policy still decides authorization.
        self.risk = 'R3' if is_destructive else 'R1' if low_impact else 'R2'
        heading = QLabel(f'{self.risk} · CONFIRMAR AÇÃO')
        heading.setObjectName('Eyebrow')
        layout.addWidget(heading)
        self.prompt = QLabel(prompt or 'Revise o efeito e os parâmetros exatos antes de aprovar.')
        self.prompt.setWordWrap(True)
        layout.addWidget(self.prompt)
        details = QPlainTextEdit()
        details.setObjectName('HudTrace')
        details.setReadOnly(True)
        details.setPlainText(json.dumps(self.pending_action,ensure_ascii=False,indent=2))
        details.setMinimumHeight(90)
        details.setMaximumHeight(160)
        details.setAccessibleName('Ação e parâmetros exatos aguardando aprovação')
        layout.addWidget(details)
        note = QLabel('A autorização vale somente para esta ação. Fechar a janela ou parar a tarefa nega o pedido.')
        note.setWordWrap(True)
        note.setObjectName('Muted')
        layout.addWidget(note)
        buttons = QHBoxLayout()
        self.btn_deny = QPushButton('Negar')
        self.btn_edit = QPushButton('Editar pedido')
        self.btn_approve = QPushButton('Aprovar')
        self.btn_approve.setObjectName('Danger' if is_destructive else 'Primary')
        self.btn_deny.clicked.connect(lambda:self.decide(False))
        self.btn_approve.clicked.connect(lambda:self.decide(True))
        self.btn_edit.clicked.connect(self._edit)
        for button in (self.btn_deny,self.btn_edit,self.btn_approve):
            button.setAccessibleName(button.text()+' ação pendente')
            buttons.addWidget(button)
        layout.addLayout(buttons)
        for label in self.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)

    def _edit(self):
        self.edit_requested.emit()
        self.decide(False)

    def decide(self, approved):
        if self.resolved:
            return
        self.resolved = True
        for button in (self.btn_deny,self.btn_edit,self.btn_approve):
            button.setEnabled(False)
        self.prompt.setText('Aprovada explicitamente.' if approved else 'Negada. Nenhuma aprovação foi enviada.')
        self.decided.emit(bool(approved))
