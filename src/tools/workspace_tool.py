"""Display bounded artifacts through an acknowledged GUI-thread dispatcher."""

import csv
import io
import json

from core.operation_control import OperationControl
from tools.registry import ToolResult


class WorkspaceTool:
    VIEWS = {
        "code": "code", "script": "code", "program": "code",
        "table": "sheet", "sheet": "sheet", "spreadsheet": "sheet", "planilha": "sheet",
        "document": "doc", "doc": "doc", "relatorio": "doc", "report": "doc", "markdown": "doc",
        "telemetry": "telemetry", "hw": "telemetry", "hardware": "telemetry",
    }

    def __init__(self, control=None, *, timeout=5.0):
        if not 0.02 <= timeout <= 10:
            raise ValueError("Prazo de exibição inválido.")
        self.control = control or OperationControl()
        self.timeout = timeout
        self.last_display = {}
        self.dispatcher = None
        try:
            from ui.workspace_dispatcher import WorkspaceDispatcher
            self.dispatcher = WorkspaceDispatcher.for_application()
        except ImportError:
            pass

    def run(self, params):
        try:
            payload = self.normalize(params)
        except (ValueError, TypeError) as error:
            return ToolResult(False, error=str(error))
        if self.dispatcher is None:
            return ToolResult(False, error="Estúdio indisponível: não há interface gráfica conectada.")
        if self.control.is_cancelled():
            return ToolResult(False, error="Exibição interrompida antes de abrir a janela.")
        result = self.dispatcher.submit(payload, self.control.cancellation_probe(), self.timeout)
        if result.ok:
            self.last_display = payload
        return result

    @classmethod
    def normalize(cls, params):
        if not isinstance(params, dict):
            raise ValueError("Parâmetros do Estúdio devem ser um objeto.")
        view = params.get("view", params.get("op", "code"))
        if not isinstance(view, str) or view.lower() not in cls.VIEWS:
            raise ValueError("Tipo de visualização inválido. Válidos: code, sheet, doc, telemetry.")
        view = cls.VIEWS[view.lower()]
        title, language = params.get("title", "Trabalho da Nyx"), params.get("language", "python")
        if not isinstance(title, str) or len(title) > 200 or not isinstance(language, str) or len(language) > 40:
            raise ValueError("Título ou linguagem inválidos ou acima do limite.")
        content, headers = params.get("content", ""), params.get("headers")
        if isinstance(content, str) and len(content) > 256000:
            raise ValueError("Conteúdo excede 256.000 caracteres.")
        if view == "sheet":
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except ValueError:
                    content = list(csv.reader(io.StringIO(content)))
            if not isinstance(content, list) or not 1 <= len(content) <= 1000:
                raise ValueError("Planilha exige de 1 a 1.000 linhas.")
            if headers is not None and (not isinstance(headers, list) or not 1 <= len(headers) <= 50
                                        or any(not isinstance(x, str) or len(x) > 200 for x in headers)):
                raise ValueError("Cabeçalhos inválidos (máximo 50).")
            mapping = isinstance(content[0], dict)
            keys = headers or (list(content[0]) if mapping else None)
            rows = []
            total = 0
            cells = 0
            for row in content:
                if (mapping and not isinstance(row, dict)) or (not mapping and not isinstance(row, (list, tuple))):
                    raise ValueError("Linhas devem ter estrutura uniforme.")
                if not 1 <= len(row) <= 50:
                    raise ValueError("Cada linha exige de 1 a 50 colunas.")
                values = [row.get(key, "") for key in keys] if mapping else row
                if any(not isinstance(value, (str, int, float, bool, type(None))) for value in values):
                    raise ValueError("Células devem conter valores simples.")
                values = [str(value) for value in values]
                cells += len(values)
                total += sum(map(len, values))
                if any(len(value) > 4000 for value in values) or total > 256000 or cells > 10000:
                    raise ValueError("Conteúdo da planilha excede os limites.")
                rows.append(values)
            content, headers = rows, [str(key)[:200] for key in keys] if keys else headers
        elif not isinstance(content, str):
            raise ValueError("Conteúdo deve ser texto.")
        return {"view": view, "title": title, "language": language, "content": content, "headers": headers}


def make_workspace_tool_func(tool):
    return tool.run
