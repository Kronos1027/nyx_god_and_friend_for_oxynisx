"""Testes para o subsistema de Workspace do Grande Sábio (Nyx)"""

import pytest
from PyQt6.QtWidgets import QApplication
import sys

from tools.workspace_tool import WorkspaceTool
from ui.workspace_window import WorkspaceWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_workspace_window_creation(qapp):
    win = WorkspaceWindow()
    assert win is not None
    assert win.tabs.count() == 4
    assert win.tabs.tabText(0) == "💻 Código"
    assert win.tabs.tabText(1) == "📊 Planilha"
    assert win.tabs.tabText(2) == "📜 Relatório"
    assert win.tabs.tabText(3) == "⚡ Telemetria"
    win.close()


def test_workspace_window_display_code(qapp):
    win = WorkspaceWindow()
    win.display_code("print('Hello Nyx')", language="python", title="Teste")
    assert "print('Hello Nyx')" in win.txt_code.toPlainText()
    assert win.tabs.currentIndex() == 0
    win.close()


def test_workspace_window_display_table(qapp):
    win = WorkspaceWindow()
    win.display_table([["CPU", "15%"], ["GPU", "98%"]], headers=["Componente", "Uso"], title="Hardware")
    assert win.table.rowCount() == 2
    assert win.table.columnCount() == 2
    assert win.table.item(0, 0).text() == "CPU"
    assert win.tabs.currentIndex() == 1
    win.close()


def test_workspace_window_display_document(qapp):
    win = WorkspaceWindow()
    win.display_document("# Análise do Grande Sábio\nTudo operacional.", title="Status")
    assert "Análise do Grande Sábio" in win.txt_doc.toPlainText()
    assert win.tabs.currentIndex() == 2
    win.close()


def test_workspace_tool_execution(qapp):
    tool = WorkspaceTool()

    # 1. Código
    res1 = tool.run({"view": "code", "content": "def add(a, b): return a + b", "language": "python", "title": "Soma"})
    assert res1.ok is True
    assert "exibida com sucesso" in res1.output.lower()

    # 2. Planilha
    res2 = tool.run({"view": "sheet", "content": "Item,Qtd,Preco\nBanana,10,5.0\nMaca,5,8.0", "title": "Estoque"})
    assert res2.ok is True
    assert "exibida com sucesso" in res2.output.lower()

    # 3. Documento
    res3 = tool.run({"view": "doc", "content": "## Relatório de Missão", "title": "Missão"})
    assert res3.ok is True
    assert "exibida com sucesso" in res3.output.lower()

    # 4. Telemetria
    res4 = tool.run({"view": "telemetry"})
    assert res4.ok is True
    assert "exibida com sucesso" in res4.output.lower()

    # 5. Erro tipo inválido
    res_err = tool.run({"view": "invalid_type", "content": "nada"})
    assert res_err.ok is False
    assert "inválido" in res_err.error.lower()
