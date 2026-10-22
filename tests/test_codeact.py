"""Testes do subsistema CodeAct e auto-cura de scripts."""

from pathlib import Path
from core.codeact import CodeActEngine
from tools.codeact_tool import CodeActTool


def test_codeact_blocks_host_execution(tmp_path):
    marker = tmp_path / "forbidden.txt"
    engine = CodeActEngine(base_workspace=tmp_path / "workspace")
    result = engine.execute_and_heal("task", f"open({str(marker)!r}, 'w').write('unsafe')")
    assert not result.ok
    assert result.meta["reason"] == "isolation_unavailable"
    assert not marker.exists()


def test_codeact_deterministic_repair_is_only_text(tmp_path):
    engine = CodeActEngine(base_workspace=tmp_path)
    assert engine._attempt_repair("print(json.dumps(1))", "name 'json' is not defined", "") == "import json\nprint(json.dumps(1))"


def test_codeact_rejects_task_and_file_escape(tmp_path):
    engine = CodeActEngine(base_workspace=tmp_path)
    assert not engine.execute_and_heal("../escape", "pass").ok
    assert not engine.execute_and_heal("task", "pass", filename="../../escape.py").ok
    assert not (tmp_path.parent / "escape.py").exists()


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
