"""Testes do subsistema CodeAct e auto-cura de scripts."""

from pathlib import Path
from core.codeact import CodeActEngine
from tools.codeact_tool import CodeActTool


def test_codeact_engine_sandbox_success(tmp_path):
    engine = CodeActEngine(base_workspace=tmp_path)
    res = engine.execute_and_heal(
        task_name="task_success",
        code="print('Hello from CodeAct!')",
        language="python",
    )
    assert res.ok is True
    assert "Hello from CodeAct!" in res.output
    assert res.meta.get("attempts") == 1


def test_codeact_engine_deterministic_healing(tmp_path):
    engine = CodeActEngine(base_workspace=tmp_path)
    # Código com import faltando propositalmente
    broken_code = "data = json.loads('{\"status\": \"ok\"}')\nprint(data['status'])"
    res = engine.execute_and_heal(
        task_name="task_healing",
        code=broken_code,
        language="python",
    )
    assert res.ok is True
    assert "ok" in res.output
    assert res.meta.get("attempts") == 2  # Corrigiu na segunda tentativa!


def test_codeact_tool_planning_and_steps(tmp_path):
    tool = CodeActTool(workspace_root=tmp_path)

    # 1. Planejar tarefa (cria todo.md)
    res_plan = tool.run({
        "action": "plan",
        "task_name": "backup_db",
        "steps": ["Criar dump do banco", "Validar integridade", "Compactar"],
    })
    assert res_plan.ok is True
    todo_file = Path(res_plan.meta["todo_file"])
    assert todo_file.exists()
    assert "Criar dump do banco" in todo_file.read_text(encoding="utf-8")

    # 2. Atualizar status do passo
    res_update = tool.run({
        "action": "update_step",
        "task_name": "backup_db",
        "step_index": 0,
        "status": "completed",
        "notes": "Dump gerado com 4.5MB",
    })
    assert res_update.ok is True
    assert "[x] Criar dump do banco" in todo_file.read_text(encoding="utf-8")
