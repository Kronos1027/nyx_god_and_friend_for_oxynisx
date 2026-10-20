"""Nyx — tools/codeact_tool.py (Ferramenta CodeAct e Execução Autônoma de Tarefas)

Permite ao agente:
- Criar tarefas com plano vivo todo.md em workspace/<tarefa>/
- Escrever e executar programas com auto-reparo em caso de erro
- Atualizar o progresso de tarefas longas
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from core.codeact import CodeActEngine
from tools.registry import ToolResult

log = logging.getLogger(__name__)


class CodeActTool:
    """Ferramenta para execução de código com auto-diagnóstico e planejamento estilo Manus/Kimi."""

    def __init__(self, workspace_root: Path = Path("workspace")) -> None:
        self.engine = CodeActEngine(base_workspace=workspace_root)
        self.active_plans: Dict[str, Any] = {}

    def run(self, params: dict) -> ToolResult:
        action = str(params.get("action", "execute")).lower()
        task_name = str(params.get("task_name", "default_task")).strip() or "default_task"

        if action in ("plan", "init_task", "todo"):
            raw_steps = params.get("steps", [])
            if isinstance(raw_steps, str):
                steps = [s.strip() for s in raw_steps.splitlines() if s.strip()]
            else:
                steps = [str(s) for s in raw_steps]

            if not steps:
                steps = ["Executar objetivo da tarefa", "Validar resultados"]

            plan = self.engine.init_task(task_name=task_name, steps=steps)
            self.active_plans[task_name] = plan
            return ToolResult(
                ok=True,
                output=f"Plano de tarefa inicializado em {plan.todo_file}.\nPassos: {len(steps)} itens.",
                meta={"task_id": plan.task_id, "todo_file": str(plan.todo_file)},
            )

        elif action in ("update_step", "step_status"):
            plan = self.active_plans.get(task_name)
            if not plan:
                # Tenta inicializar se não existir
                plan = self.engine.init_task(task_name=task_name, steps=["Passo principal"])
                self.active_plans[task_name] = plan

            idx = int(params.get("step_index", 0))
            status = str(params.get("status", "completed")).lower()
            notes = params.get("notes")
            plan.update_item_status(idx, status=status, notes=notes)
            return ToolResult(
                ok=True,
                output=f"Passo {idx + 1} da tarefa '{task_name}' atualizado para '{status}'.",
                meta={"task_name": task_name, "step_index": idx, "status": status},
            )

        elif action in ("execute", "run", "code"):
            code = params.get("code", "")
            if not code:
                return ToolResult(ok=False, error="Parâmetro 'code' é obrigatório para execução.")

            language = str(params.get("language", "python")).lower()
            filename = params.get("filename")
            return self.engine.execute_and_heal(
                task_name=task_name,
                code=code,
                language=language,
                filename=filename,
            )

        return ToolResult(
            ok=False,
            error=f"Ação CodeAct '{action}' desconhecida. Válidas: plan, execute, update_step.",
        )


def make_codeact_tool_func(tool: CodeActTool):
    def _run(params: dict) -> ToolResult:
        return tool.run(params)

    return _run
