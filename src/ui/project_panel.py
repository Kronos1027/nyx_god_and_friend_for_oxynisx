"""Project versions in the existing studio; file I/O runs off the GUI thread."""

from pathlib import Path
import threading

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QListWidget,
    QPlainTextEdit,
    QSplitter,
    QFileDialog,
    QMessageBox,
)

from core.project_snapshot import ProjectSnapshot, SnapshotFile
from core.project_store import ProjectStore


class ProjectJob(QThread):
    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation
        self.value = None
        self.error = None

    def run(self):
        try:
            self.value = self.operation()
        except Exception as error:
            self.error = str(error)


class ProjectPanel(QWidget):
    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = Path(directory)
        self.job = None
        self.snapshot = None
        self.cancelled = threading.Event()
        layout = QVBoxLayout(self)
        self.projects = QComboBox()
        self.versions = QComboBox()
        layout.addWidget(QLabel("Projeto e versão"))
        layout.addWidget(self.projects)
        layout.addWidget(self.versions)
        actions = QHBoxLayout()
        self.buttons = []
        for text, callback in (
            ("Importar pasta", self.import_folder),
            ("Nova versão da pasta", self.save_folder),
            ("Restaurar versão", self.restore),
            ("Exportar ZIP", self.export),
            ("Atualizar", self.refresh),
            ("Excluir projeto", self.delete),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            self.buttons.append(button)
            actions.addWidget(button)
        layout.addLayout(actions)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.files = QListWidget()
        self.preview = QPlainTextEdit()
        self.preview.setFont(QFont("Consolas", 10))
        self.preview.setReadOnly(True)
        split.addWidget(self.files)
        split.addWidget(self.preview)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        self.status = QLabel(
            "Importe uma pasta ou guarde o código como projeto. Testes não executados."
        )
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.projects.currentIndexChanged.connect(self.select_project)
        self.versions.currentIndexChanged.connect(self.select_version)
        self.files.currentRowChanged.connect(self.show_file)
        self.update_controls()

    def update_controls(self):
        idle = self.job is None
        for index, button in enumerate(self.buttons):
            available = index in (0, 4) or bool(self.projects.currentData())
            if index in (2, 3):
                available = self.snapshot is not None
            button.setEnabled(idle and available)
        self.projects.setEnabled(idle)
        self.versions.setEnabled(idle)

    def start(self, operation, done):
        if self.job is not None:
            return
        self.cancelled.clear()
        self.status.setText("Processando arquivos…")
        for control in (*self.buttons, self.projects, self.versions):
            control.setEnabled(False)
        self.done = done
        self.job = ProjectJob(operation, self)
        self.job.finished.connect(self.finish)
        self.job.start()

    def finish(self):
        worker, self.job = self.job, None
        for control in (*self.buttons, self.projects, self.versions):
            control.setEnabled(True)
        if worker.error is not None:
            self.status.setText("Falha: " + worker.error)
        else:
            self.done(worker.value)
        self.update_controls()
        worker.deleteLater()

    def store(self):
        return ProjectStore(self.directory)

    def refresh(self, selected=None):
        chosen = selected if isinstance(selected, str) else self.projects.currentData()

        def loaded(rows):
            self.projects.blockSignals(True)
            self.projects.clear()
            for row in rows:
                self.projects.addItem(row["title"], row["id"])
            index = self.projects.findData(chosen)
            if index >= 0:
                self.projects.setCurrentIndex(index)
            self.projects.blockSignals(False)
            self.select_project()

        self.start(lambda: self.store().projects(), loaded)

    def select_project(self, *_):
        identifier = self.projects.currentData()
        self.snapshot = None
        self.files.clear()
        self.preview.clear()
        if not identifier:
            self.versions.clear()
            self.status.setText("Nenhum projeto salvo. Importe uma pasta ou guarde o código.")
            return

        def loaded(rows):
            self.versions.blockSignals(True)
            self.versions.clear()
            for row in rows:
                self.versions.addItem(
                    f"v{row['number']} — {row['note']} ({row['bytes']} bytes)", row["number"]
                )
            self.versions.blockSignals(False)
            self.select_version()

        self.start(lambda: self.store().versions(identifier), loaded)

    def select_version(self, *_):
        identifier, number = self.projects.currentData(), self.versions.currentData()
        self.snapshot = None
        self.files.clear()
        self.preview.clear()
        if not identifier or number is None:
            return

        def loaded(snapshot):
            self.snapshot = snapshot
            self.files.clear()
            self.files.addItems([item.name for item in snapshot.files])
            if snapshot.files:
                self.files.setCurrentRow(0)
            self.status.setText(
                f"v{number}: {len(snapshot.files)} arquivos; {snapshot.manifest()['bytes']} bytes. "
                f"{len(snapshot.skipped)} entradas excluídas. Testes não executados."
            )

        self.start(lambda: self.store().load(identifier, number), loaded)

    def show_file(self, index):
        if self.snapshot is None or not 0 <= index < len(self.snapshot.files):
            self.preview.clear()
            return
        item = self.snapshot.files[index]
        try:
            text = item.content[:128000].decode("utf-8")
            if "\x00" in text:
                raise ValueError("binary")
        except (UnicodeError, ValueError):
            text = f"Arquivo binário: {len(item.content)} bytes. Disponível na exportação ZIP."
        else:
            if len(item.content) > 128000:
                text += "\n\n[Prévia limitada a 128.000 bytes]"
        self.preview.setPlainText(text)

    def capture(self, path):
        return ProjectSnapshot.capture(path, cancelled=self.cancelled.is_set)

    def import_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Importar cópia de projeto")
        if path:
            self.start(
                lambda: self.store().create(Path(path).name[:120], self.capture(path)), self.refresh
            )

    def save_folder(self):
        identifier = self.projects.currentData()
        if not identifier:
            self.status.setText("Selecione um projeto primeiro.")
            return
        path = QFileDialog.getExistingDirectory(self, "Salvar nova versão a partir de uma pasta")
        if path:
            self.start(
                lambda: self.store().save(identifier, self.capture(path)),
                lambda _: self.refresh(identifier),
            )

    def save_code(self, title, code, filename="main.py"):
        self.start(
            lambda: self.store().create(
                title[:120] or "Código",
                ProjectSnapshot((SnapshotFile(filename, code.encode("utf-8")),)),
            ),
            self.refresh,
        )

    def restore(self):
        identifier, number = self.projects.currentData(), self.versions.currentData()
        if identifier and number is not None:
            self.start(
                lambda: self.store().restore(identifier, number), lambda _: self.refresh(identifier)
            )

    def export(self):
        if self.snapshot is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar cópia ZIP (arquivo novo)", "projeto.zip", "ZIP (*.zip)"
        )
        if path:
            snapshot = self.snapshot
            self.start(
                lambda: snapshot.export_zip(path),
                lambda _: self.status.setText(
                    "ZIP exportado e conteúdo preservado. Testes não executados."
                ),
            )

    def delete(self):
        identifier = self.projects.currentData()
        if not identifier:
            return
        answer = QMessageBox.question(
            self,
            "Excluir histórico do projeto",
            f"Excluir todas as versões de ‘{self.projects.currentText()}’ do catálogo? Arquivos de origem e ZIPs não serão apagados.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.start(lambda: self.store().delete(identifier), lambda _: self.refresh())
