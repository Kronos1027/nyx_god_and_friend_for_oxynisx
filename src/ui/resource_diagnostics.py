"""Explicit resource consultation outside the UI thread; no monitoring loop."""
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, QTableWidget,
                            QTableWidgetItem, QHeaderView, QAbstractItemView)


class _Signals(QObject):
    finished = pyqtSignal(object)


class _Inspection(QRunnable):
    def __init__(self, include_processes):
        super().__init__()
        self.include_processes = include_processes
        self.signals = _Signals()

    def run(self):
        from core.resource_diagnostics import diagnose_resources
        try:
            report = diagnose_resources(self.include_processes)
        except Exception as exc:
            report = {'errors': ['Diagnóstico indisponível: ' + type(exc).__name__]}
        self.signals.finished.emit(report)


class ResourceDiagnosticsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Diagnóstico de memória')
        self.resize(780, 440)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.worker = None
        layout = QVBoxLayout(self)
        note = QLabel('Consulta única dos recursos. “Consultar consumo por aplicativo” lê nomes de processos e RAM. '
                      'Valores aproximados de working set podem contar memória compartilhada mais de uma vez. '
                      'Nenhum aplicativo será fechado; os dados ficam somente nesta janela.')
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        self.summary = QLabel('Clique em Atualizar recursos para consultar.')
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Processo', 'Instâncias', 'RAM aproximada (MiB)'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.refresh_button = QPushButton('Atualizar recursos')
        self.refresh_button.clicked.connect(lambda: self.refresh(False))
        layout.addWidget(self.refresh_button)
        self.process_button = QPushButton('Consultar consumo por aplicativo')
        self.process_button.clicked.connect(lambda: self.refresh(True))
        layout.addWidget(self.process_button)

    def refresh(self, include_processes=False):
        if self.worker is not None:
            return
        self.refresh_button.setEnabled(False)
        self.process_button.setEnabled(False)
        self.summary.setText('Consultando recursos…')
        self.table.setRowCount(0)
        self.worker = _Inspection(include_processes)
        self.worker.signals.finished.connect(self._finished)
        self.pool.start(self.worker)

    def _finished(self, report):
        self.worker = None
        self.refresh_button.setEnabled(True)
        self.process_button.setEnabled(True)
        resources = report.get('resources', {})
        def gib(value):
            return f'{value / 1024**3:.2f} GiB' if type(value) is int else 'não disponível'
        text = (f"RAM livre: {gib(resources.get('ram_available_bytes'))} · "
                f"VRAM livre: {gib(resources.get('vram_free_bytes'))}\n" + report.get('reason', ''))
        consumers = report.get('consumers')
        if consumers is not None:
            rows = consumers['rows']
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                for column, value in enumerate((row['name'], row['processes'], f"{row['rss_bytes'] / 1024**2:.0f}")):
                    self.table.setItem(index, column, QTableWidgetItem(str(value)))
            text += f"\n{consumers['scanned']} processos consultados; {consumers['unavailable']} sem medida."
            if consumers['truncated']:
                text += ' Consulta parcial: limite de tempo/quantidade atingido.'
        elif not report.get('processes_requested'):
            text += '\nNomes de processos não consultados.'
        if report.get('errors'):
            text += '\n' + '\n'.join(report['errors'])
        self.summary.setText(text)
