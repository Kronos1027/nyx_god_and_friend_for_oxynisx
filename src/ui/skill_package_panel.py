"""Inspect inactive skill packages; all storage work stays off the Qt thread."""

from pathlib import Path
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
                            QPushButton, QLabel, QListWidget, QPlainTextEdit, QSplitter, QFileDialog)

from core.skill_package_store import SkillPackageStore
from ui.project_panel import ProjectJob


class SkillPackagePanel(QWidget):
    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = Path(directory)
        self.job = None
        self.package = None
        self.cancelled = threading.Event()
        layout = QVBoxLayout(self)
        self.notice = QLabel("Pacotes importados permanecem inativos. Scripts não são executados nem testados aqui.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.query = QLineEdit()
        self.query.setMaxLength(200)
        self.query.setPlaceholderText("Buscar nome ou descrição")
        self.query.returnPressed.connect(self.refresh)
        layout.addWidget(self.query)
        self.packages, self.versions = QComboBox(), QComboBox()
        layout.addWidget(self.packages)
        layout.addWidget(self.versions)
        actions = QHBoxLayout()
        self.import_button = QPushButton("Importar pacote / nova versão")
        self.refresh_button = QPushButton("Buscar / atualizar")
        self.export_button = QPushButton("Exportar versão ZIP")
        self.import_button.clicked.connect(self.import_folder)
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button.clicked.connect(self.export)
        for button in (self.import_button, self.refresh_button, self.export_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.details = QLabel("Nenhum pacote selecionado.")
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.files, self.preview = QListWidget(), QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Selecione um recurso para inspecionar o pacote antes de usá-lo.")
        self.files.setAccessibleName("Recursos da habilidade selecionada")
        splitter.addWidget(self.files)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.status = QLabel("Importe uma pasta com SKILL.md ou atualize o catálogo.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.packages.currentIndexChanged.connect(self.select_package)
        self.versions.currentIndexChanged.connect(self.select_version)
        self.files.currentRowChanged.connect(self.show_file)
        self.controls = (self.query, self.packages, self.versions, self.import_button,
                         self.refresh_button, self.export_button)
        self.update_controls()

    def store(self):
        return SkillPackageStore(self.directory)

    def update_controls(self):
        for control in self.controls:
            control.setEnabled(self.job is None)
        self.export_button.setEnabled(self.job is None and self.package is not None)

    def start(self, operation, done):
        if self.job is not None:
            return
        self.cancelled.clear()
        self.status.setText("Processando pacote…")
        self.done = done
        self.job = ProjectJob(operation, self)
        self.job.finished.connect(self.finish)
        self.update_controls()
        self.job.start()

    def finish(self):
        worker, self.job = self.job, None
        try:
            if worker.error is not None:
                self.status.setText("Falha: " + worker.error)
            else:
                self.done(worker.value)
        finally:
            self.update_controls()
            worker.deleteLater()

    def clear_preview(self):
        self.package = None
        self.files.clear()
        self.preview.clear()
        self.details.setText("Nenhum pacote selecionado.")

    def refresh(self, selected=None):
        chosen = selected if isinstance(selected, str) else self.packages.currentData()
        query = self.query.text().casefold().split()

        def loaded(rows):
            self.packages.blockSignals(True)
            self.packages.clear()
            for row in rows:
                if all(word in (row["name"] + " " + row["description"]).casefold() for word in query):
                    self.packages.addItem(row["name"], row["name"])
            index = self.packages.findData(chosen)
            if index >= 0:
                self.packages.setCurrentIndex(index)
            self.packages.blockSignals(False)
            self.select_package()

        self.start(lambda: self.store().list_packages(), loaded)

    def select_package(self, *_):
        name = self.packages.currentData()
        self.clear_preview()
        if not name:
            self.versions.clear()
            self.status.setText("Nenhum pacote encontrado. Importe uma pasta ou ajuste a busca.")
            return

        def loaded(rows):
            self.versions.blockSignals(True)
            self.versions.clear()
            for row in rows:
                self.versions.addItem(f"v{row['version']} · Inativa · {row['bytes']} bytes", row)
            self.versions.blockSignals(False)
            self.select_version()

        self.start(lambda: self.store().versions(name), loaded)

    def select_version(self, *_):
        name, row = self.packages.currentData(), self.versions.currentData()
        self.clear_preview()
        if not name or not row:
            return

        def loaded(package):
            self.package = package
            self.details.setText(f"{package.metadata.description}\nOrigem declarada: {row['origin']}\nSHA-256: {row['digest']}")
            self.files.addItems([item.name for item in package.snapshot.files])
            if package.snapshot.files:
                self.files.setCurrentRow(0)
            self.status.setText(f"v{row['version']} inativa. Estrutura e integridade conferidas; testes funcionais não executados. "
                                f"{len(package.snapshot.skipped)} entradas excluídas na captura.")

        self.start(lambda: self.store().load(name, row["version"]), loaded)

    def show_file(self, index):
        if self.package is None or not 0 <= index < len(self.package.snapshot.files):
            self.preview.clear()
            return
        item = self.package.snapshot.files[index]
        try:
            text = item.content.decode("utf-8")
            if "\x00" in text:
                raise ValueError("binary")
        except (UnicodeError, ValueError):
            text = f"Arquivo binário: {len(item.content)} bytes; incluído na exportação."
        if len(text) > 16000:
            text = text[:16000] + "\n[Prévia limitada a 16.000 caracteres]"
        self.preview.setPlainText(text)

    def import_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Importar pacote com SKILL.md")
        if path:
            def imported(result):
                self.query.clear()
                self.refresh(result["name"])
            self.start(lambda: self.store().import_directory(path, cancelled=self.cancelled.is_set), imported)

    def export(self):
        if self.package is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar pacote (arquivo novo)",
                                             self.package.metadata.name + ".zip", "ZIP (*.zip)")
        if path:
            package = self.package
            self.start(lambda: package.export_zip(path),
                       lambda _: self.status.setText("Versão exportada. Pacote continua inativo; scripts não executados."))
