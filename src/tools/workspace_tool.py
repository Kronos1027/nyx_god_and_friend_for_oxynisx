"""Nyx — tools/workspace_tool.py (Ferramenta do Grande Sábio para Canvas Visual)

Permite ao modelo ou agente abrir sub-janelas interativas com código, planilhas,
documentos ou telemetria visual na interface gráfica.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tools.registry import ToolResult

log = logging.getLogger(__name__)


class WorkspaceTool:
    """Ferramenta para exibição e criação de sub-janelas do Grande Sábio."""

    def __init__(self) -> None:
        self.last_display: dict[str, Any] = {}

    def run(self, params: dict) -> ToolResult:
        view = params.get("view", params.get("op", "code")).lower()
        title = params.get("title", "Trabalho do Grande Sábio")
        content = params.get("content", "")
        language = params.get("language", "python")
        headers = params.get("headers", None)

        valid_views = {
            "code", "script", "program",
            "table", "sheet", "spreadsheet", "planilha",
            "document", "doc", "relatorio", "report", "markdown",
            "telemetry", "hw", "hardware",
        }
        if view not in valid_views:
            return ToolResult(
                ok=False,
                output="",
                error=f"Tipo de visualização '{view}' inválido. Válidos: code, sheet, doc, telemetry.",
            )

        self.last_display = {
            "view": view,
            "title": title,
            "content": content,
            "language": language,
            "headers": headers,
        }

        # Tenta acionar a interface visual se QApplication estiver rodando
        try:
            from PyQt6.QtWidgets import QApplication

            if QApplication.instance():
                from ui.workspace_window import WorkspaceWindow

                win = WorkspaceWindow.get_instance()
                if view in ("code", "script", "program"):
                    win.display_code(str(content), title=title, language=language)
                elif view in ("table", "sheet", "spreadsheet", "planilha"):
                    data = content
                    if isinstance(content, str):
                        try:
                            data = json.loads(content)
                        except Exception:
                            # Tenta separar por linhas e vírgulas
                            data = [line.split(",") for line in content.strip().splitlines()]
                    win.display_table(data, headers=headers, title=title)
                elif view in ("document", "doc", "relatorio", "report", "markdown"):
                    win.display_document(str(content), title=title)
                elif view in ("telemetry", "hw", "hardware"):
                    win.refresh_telemetry()
                    win.tabs.setCurrentIndex(3)
                    win.show()
                else:
                    win.display_document(str(content), title=title)
        except Exception as exc:
            log.info(f"Workspace executado em modo headless/sem UI ativa: {exc}")

        return ToolResult(
            ok=True,
            output=f"Janela de trabalho '{view}' exibida com sucesso: {title}",
            meta={"view": view, "title": title},
        )


def make_workspace_tool_func(tool: WorkspaceTool):
    def _run(params: dict) -> ToolResult:
        return tool.run(params)

    return _run
