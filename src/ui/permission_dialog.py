"""Nyx — ui/permission_dialog.py (Fase 5: Diálogo de Confirmação Explícita)

Diálogo de confirmação por UI com exibição clara e destacada:
- Exibe o comando/params exatos antes da execução.
- Alerta visual de perigo para ações destrutivas (vermelho com aviso não-reversível).
- Garante que confirmações sensíveis venham de interação explícita do usuário (clique).
"""

from __future__ import annotations

import json
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QFrame,
    QWidget,
)


class PermissionDialog(QDialog):
    """Diálogo modal para aprovação explícita de ações sensíveis e destrutivas."""

    def __init__(
        self,
        pending_action: dict,
        prompt: str | None = None,
        is_destructive: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pending_action = pending_action
        self.is_destructive = is_destructive
        self.approved = False

        self.setWindowTitle("Nyx — Confirmação de Segurança")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(460)

        self._init_ui(prompt)

    def _init_ui(self, prompt: str | None) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)

        # Card de fundo com estilo cyberpunk / dark mode
        card = QFrame(self)
        border_color = "#EF4444" if self.is_destructive else "#10B981"
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: #0F172A;
                border: 2px solid {border_color};
                border-radius: 12px;
            }}
            """
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        # Cabeçalho
        title_box = QHBoxLayout()
        icon = "⚠️" if self.is_destructive else "🛡️"
        title_text = "AÇÃO DESTRUTIVA" if self.is_destructive else "SOLICITAÇÃO DE PERMISSÃO"
        title_color = "#EF4444" if self.is_destructive else "#10B981"

        header_lbl = QLabel(f"{icon} {title_text}", card)
        header_lbl.setStyleSheet(
            f"color: {title_color}; font-weight: bold; font-size: 14px; border: none;"
        )
        title_box.addWidget(header_lbl)
        title_box.addStretch()
        card_layout.addLayout(title_box)

        # Prompt descritivo
        display_prompt = prompt or "Nyx solicita autorização para executar a seguinte ação:"
        prompt_lbl = QLabel(display_prompt, card)
        prompt_lbl.setWordWrap(True)
        prompt_lbl.setStyleSheet("color: #E2E8F0; font-size: 12px; border: none;")
        card_layout.addWidget(prompt_lbl)

        if self.is_destructive:
            warning_lbl = QLabel(
                "Atenção: Esta ação pode alterar ou excluir dados de forma irreversível.",
                card,
            )
            warning_lbl.setWordWrap(True)
            warning_lbl.setStyleSheet(
                "color: #F87171; font-size: 11px; font-weight: bold; border: none;"
            )
            card_layout.addWidget(warning_lbl)

        # Bloco de código com o comando/parâmetros exatos
        details_box = QTextEdit(card)
        details_box.setReadOnly(True)
        details_box.setFixedHeight(120)
        formatted_json = json.dumps(self.pending_action, indent=2, ensure_ascii=False)
        details_box.setPlainText(formatted_json)
        details_box.setStyleSheet(
            """
            QTextEdit {
                background-color: #1E293B;
                color: #38BDF8;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
            }
            """
        )
        card_layout.addWidget(details_box)

        # Botões de Ação
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_deny = QPushButton("Recusar", card)
        self.btn_deny.setStyleSheet(
            """
            QPushButton {
                background-color: #334155;
                color: #F1F5F9;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            """
        )
        self.btn_deny.clicked.connect(self._on_deny)

        self.btn_approve = QPushButton(
            "Aprovar Destruição" if self.is_destructive else "Autorizar", card
        )
        approve_bg = "#DC2626" if self.is_destructive else "#059669"
        approve_hover = "#EF4444" if self.is_destructive else "#10B981"
        self.btn_approve.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {approve_bg};
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 18px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {approve_hover};
            }}
            """
        )
        self.btn_approve.clicked.connect(self._on_approve)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_deny)
        btn_layout.addWidget(self.btn_approve)
        card_layout.addLayout(btn_layout)

        outer_layout.addWidget(card)

    def _on_approve(self) -> None:
        self.approved = True
        self.accept()

    def _on_deny(self) -> None:
        self.approved = False
        self.reject()

    @classmethod
    def ask_confirmation(
        cls,
        pending_action: dict,
        prompt: str | None = None,
        is_destructive: bool = False,
        parent: QWidget | None = None,
    ) -> bool:
        """Exibe o diálogo modal e retorna True se aprovado."""
        dialog = cls(pending_action, prompt=prompt, is_destructive=is_destructive, parent=parent)
        dialog.exec()
        return dialog.approved
