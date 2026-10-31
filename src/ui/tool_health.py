"""Read-only health inspection with explicit reset of transient pauses."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)


class ToolHealthDialog(QDialog):
    def __init__(self, registry, audit, parent=None):
        super().__init__(parent)
        self.registry, self.audit = registry, audit
        self.setWindowTitle('Saúde das ferramentas')
        self.resize(820, 440)
        layout = QVBoxLayout(self)
        note = QLabel('Falhas pausam somente a operação e o alvo afetados. Resultado não verificado exige observação. '
                      'Reativar não repete ações, não libera permissões nem remove a parada de emergência.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Ferramenta', 'Ação', 'Alvo', 'Estado', 'Falhas', 'Sem verificação', 'Espera (s)'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        refresh = QPushButton('Atualizar estado')
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        self.reset_button = QPushButton('Reativar operações pausadas')
        self.reset_button.clicked.connect(self.reset)
        layout.addWidget(self.reset_button)
        self.refresh()

    def refresh(self):
        rows = self.registry.breaker.snapshot()
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, key in enumerate(('tool', 'action', 'target', 'state', 'failures', 'unverified', 'retry_after_s')):
                self.table.setItem(index, column, QTableWidgetItem(str(row[key])))
        disabled = sorted(self.registry.disabled_tools)
        self.summary.setText(('Desativadas manualmente: ' + ', '.join(disabled)) if disabled else
                             ('Nenhuma falha pendente registrada.' if not rows else 'Estado consultado nesta sessão.'))
        self.reset_button.setEnabled(any(row['failures'] >= 3 for row in rows))

    def reset(self):
        self.registry.breaker.reset()
        self.audit.log_event('circuit_breaker_reset', source='tool_health_dialog')
        self.refresh()
