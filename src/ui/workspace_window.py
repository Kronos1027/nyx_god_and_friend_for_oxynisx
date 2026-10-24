"""Nyx — ui/workspace_window.py (O Grande Sábio - Sub-Janela de Trabalho e Criação)

Interface visual multifuncional inspirada no 'Grande Sábio' de Tensura:
- Exibe programas, scripts e códigos gerados sem execução no host.
- Exibe planilhas e tabelas dinâmicas interativas com exportação CSV.
- Exibe relatórios analíticos formatados em Markdown.
- Monitora telemetria em tempo real (GPU RTX 3060, CPU, VRAM).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class WorkspaceWindow(QWidget):
    """Sub-janela do Grande Sábio para exibição de trabalho, código e planilhas."""

    _instance: WorkspaceWindow | None = None

    @classmethod
    def get_instance(cls, parent: QWidget | None = None) -> WorkspaceWindow:
        if cls._instance is None:
            cls._instance = cls(parent)
        return cls._instance

    def __init__(self, parent: QWidget | None = None, *, project_directory=None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Nyx — Estúdio")
        self.resize(1060, 680)
        from ui.desktop_theme import desktop_stylesheet
        self.setObjectName("WorkspaceSurface")
        self.setStyleSheet(parent.styleSheet() if parent and parent.styleSheet() else desktop_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Cabeçalho Cyberpunk
        header_layout = QHBoxLayout()
        lbl_title = QLabel("Estúdio / Nyx", self)
        lbl_title.setObjectName("PageTitle")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        self.lbl_status = QLabel("Pronto para sintetizar.", self)
        self.lbl_status.setObjectName("Muted")
        header_layout.addWidget(self.lbl_status)
        layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        self._init_code_tab()
        self._init_table_tab()
        self._init_document_tab()
        self._init_telemetry_tab()
        from app_paths import user_data_dir
        from ui.project_panel import ProjectPanel
        self.projects_panel = ProjectPanel(project_directory or user_data_dir() / "data" / "studio", self)
        self.tabs.addTab(self.projects_panel, "Projetos")
        self.tabs.currentChanged.connect(self._project_tab_changed)
        self._code_title, self._code_language = "Código", "python"
        self.telemetry_job = None
        from ui.studio_lifecycle import StudioLifecycle
        StudioLifecycle.register(self)

    # ----------------------------------------------------------------------
    # Aba 1: Código / Script
    # ----------------------------------------------------------------------
    def _init_code_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        self.txt_code = QPlainTextEdit(tab)
        self.txt_code.setFont(QFont("Consolas", 11))
        self.txt_code.setPlaceholderText("# O código ou programa gerado pela Nyx aparecerá aqui...")
        layout.addWidget(self.txt_code)

        actions_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Copiar Código", tab)
        btn_copy.setObjectName("btnSecondary")
        btn_copy.clicked.connect(self._copy_code)
        actions_layout.addWidget(btn_copy)

        btn_save = QPushButton("💾 Salvar Arquivo", tab)
        btn_save.setObjectName("btnSecondary")
        btn_save.clicked.connect(self._save_code_to_file)
        actions_layout.addWidget(btn_save)
        btn_project = QPushButton("Guardar como projeto", tab)
        btn_project.clicked.connect(self._save_code_project)
        actions_layout.addWidget(btn_project)

        actions_layout.addStretch()

        self.btn_run = QPushButton("▶️ Executar Script", tab)
        self.btn_run.setEnabled(False)
        self.btn_run.setToolTip("Execução indisponível: o executor isolado ainda não está integrado.")
        self.btn_run.clicked.connect(self._run_code)
        actions_layout.addWidget(self.btn_run)

        layout.addLayout(actions_layout)
        self.tabs.addTab(tab, "💻 Código")

    # ----------------------------------------------------------------------
    # Aba 2: Planilha / Tabela
    # ----------------------------------------------------------------------
    def _init_table_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        self.table = QTableWidget(tab)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        actions_layout = QHBoxLayout()
        btn_export = QPushButton("💾 Exportar para CSV", tab)
        btn_export.setObjectName("btnSecondary")
        btn_export.clicked.connect(self._export_table_csv)
        actions_layout.addWidget(btn_export)

        btn_clear = QPushButton("🗑️ Limpar", tab)
        btn_clear.setObjectName("btnSecondary")
        btn_clear.clicked.connect(self.table.clear)
        actions_layout.addWidget(btn_clear)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)
        self.tabs.addTab(tab, "📊 Planilha")

    # ----------------------------------------------------------------------
    # Aba 3: Relatório / Documento
    # ----------------------------------------------------------------------
    def _init_document_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        self.txt_doc = QTextBrowser(tab)
        self.txt_doc.setOpenExternalLinks(True)
        layout.addWidget(self.txt_doc)

        self.tabs.addTab(tab, "📜 Relatório")

    # ----------------------------------------------------------------------
    # Aba 4: Telemetria de Hardware
    # ----------------------------------------------------------------------
    def _init_telemetry_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        self.lbl_hw_info = QLabel("Carregando telemetria de hardware...", tab)
        self.lbl_hw_info.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_hw_info.setObjectName("Muted")
        layout.addWidget(self.lbl_hw_info)

        btn_refresh = QPushButton("🔄 Atualizar Diagnóstico", tab)
        btn_refresh.setObjectName("btnSecondary")
        btn_refresh.clicked.connect(self.refresh_telemetry)
        self.btn_refresh_telemetry = btn_refresh
        layout.addWidget(btn_refresh)
        layout.addStretch()

        self.tabs.addTab(tab, "⚡ Telemetria")

    # ----------------------------------------------------------------------
    # Métodos Públicos de Atualização
    # ----------------------------------------------------------------------
    def display_code(self, code: str, title: str = "Script", language: str = "python") -> None:
        self._code_title, self._code_language = title, language
        self.txt_code.setPlainText(code)
        self.lbl_status.setText(f"Código ({language}): {title}")
        self.tabs.setCurrentIndex(0)
        self.show()
        self.raise_()

    def display_table(self, data: list[list[Any]] | list[dict[str, Any]], headers: list[str] | None = None, title: str = "Dados") -> None:
        self.table.clear()
        if not data:
            return

        if isinstance(data[0], dict):
            keys = headers or list(data[0].keys())
            self.table.setColumnCount(len(keys))
            self.table.setHorizontalHeaderLabels(keys)
            self.table.setRowCount(len(data))
            for row_idx, item in enumerate(data):
                for col_idx, key in enumerate(keys):
                    val = str(item.get(key, ""))
                    self.table.setItem(row_idx, col_idx, QTableWidgetItem(val))
        elif isinstance(data[0], (list, tuple)):
            num_cols = max(len(row) for row in data)
            self.table.setColumnCount(num_cols)
            if headers:
                self.table.setHorizontalHeaderLabels(headers)
            self.table.setRowCount(len(data))
            for row_idx, row in enumerate(data):
                for col_idx, val in enumerate(row):
                    self.table.setItem(row_idx, col_idx, QTableWidgetItem(str(val)))

        self.lbl_status.setText(f"Planilha: {title} ({len(data)} linhas)")
        self.tabs.setCurrentIndex(1)
        self.show()
        self.raise_()

    def display_document(self, markdown_text: str, title: str = "Relatório") -> None:
        self.txt_doc.setMarkdown(markdown_text)
        self.lbl_status.setText(f"Relatório: {title}")
        self.tabs.setCurrentIndex(2)
        self.show()
        self.raise_()

    def refresh_telemetry(self) -> None:
        if self.telemetry_job is not None:
            return
        from tools.project_watch_tool import ProjectWatchTool
        from ui.project_panel import ProjectJob
        self.lbl_hw_info.setText("Consultando telemetria…")
        self.btn_refresh_telemetry.setEnabled(False)
        self.telemetry_job = ProjectJob(lambda: ProjectWatchTool().run({}), self)
        self.telemetry_job.finished.connect(self._telemetry_finished)
        self.telemetry_job.start()

    def _telemetry_finished(self):
        worker, self.telemetry_job = self.telemetry_job, None
        res = worker.value
        self.btn_refresh_telemetry.setEnabled(True)
        if worker.error is None and res and res.ok:
            self.lbl_hw_info.setText(res.output)
            self.lbl_status.setText("Telemetria atualizada em tempo real.")
        else:
            self.lbl_hw_info.setText("Falha ao obter telemetria.")
        worker.deleteLater()

    # ----------------------------------------------------------------------
    # Ações Internas
    # ----------------------------------------------------------------------
    def _copy_code(self) -> None:
        from PyQt6.QtWidgets import QApplication
        text = self.txt_code.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
                self.lbl_status.setText("Código copiado para a área de transferência!")

    def _save_code_to_file(self) -> None:
        text = self.txt_code.toPlainText()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Script", "script.py", "Todos os Arquivos (*.*)")
        if path:
            Path(path).write_text(text, encoding="utf-8")
            self.lbl_status.setText(f"Salvo em: {Path(path).name}")

    def _run_code(self) -> None:
        # A UI click does not turn a subprocess into a security sandbox.
        self.lbl_status.setText("Execução bloqueada: o executor isolado ainda não está integrado.")

    def _project_tab_changed(self, index):
        if index == 4 and self.projects_panel.projects.count() == 0 and self.projects_panel.job is None:
            self.projects_panel.refresh()

    def _save_code_project(self):
        text = self.txt_code.toPlainText()
        if not text or self.projects_panel.job is not None:
            return
        filenames = {"python": "main.py", "javascript": "main.js", "html": "index.html", "css": "style.css"}
        self.projects_panel.save_code(self._code_title, text, filenames.get(self._code_language, "code.txt"))
        self.tabs.setCurrentIndex(4)

    def closeEvent(self, event):
        if self.telemetry_job is not None:
            self.lbl_status.setText("Aguarde o término da consulta de telemetria para fechar.")
            event.ignore()
            return
        if self.projects_panel.job is not None:
            self.projects_panel.cancelled.set()
            self.projects_panel.status.setText("Aguarde o término da operação para fechar. Cópia cancelada quando possível.")
            event.ignore()
            return
        super().closeEvent(event)

    def _export_table_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Salvar Planilha", "planilha.csv", "Arquivos CSV (*.csv)")
        if not path:
            return
        rows = self.table.rowCount()
        cols = self.table.columnCount()
        headers = [self.table.horizontalHeaderItem(c).text() if self.table.horizontalHeaderItem(c) else f"Col{c}" for c in range(cols)]

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in range(rows):
                row_data = [self.table.item(r, c).text() if self.table.item(r, c) else "" for c in range(cols)]
                writer.writerow(row_data)

        self.lbl_status.setText(f"Planilha exportada com sucesso: {Path(path).name}")
