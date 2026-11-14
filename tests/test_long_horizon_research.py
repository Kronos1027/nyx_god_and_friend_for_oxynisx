"""Stress tests of long tasks: many *real* sandbox reads, scripted local model.

Not a claim that Qwen can autonomously solve 48 arbitrary tasks.
"""
import json
import tracemalloc

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_runner import TaskRunner
from tools.file_tool import FileTool
from tools.registry import ToolRegistry, ToolSpec


def reply(tool="none", params=None):
    return json.dumps({"emotion": "idle", "speech_output": "Resumo verificável",
                       "action": {"type": tool, "params": params or {}},
                       "requires_confirmation": False})


def prepare(tmp_path, total):
    root = tmp_path / "fixtures"
    root.mkdir()
    paths = []
    for i in range(total):
        p = root / f"doc_{i:02d}.txt"
        p.write_text(f"evidência-{i:02d}")
        paths.append(p)
    registry = ToolRegistry()
    files = FileTool([root])
    registry.register(ToolSpec("read_file", "read-only", sensitive=False), files.read_file)
    llm = OfflineLLM([reply("read_file", {"path": str(path)}) for path in paths] + [reply()])
    loop = AgentLoop(llm, registry, AuditLogger(tmp_path / "audit"))
    runner = TaskRunner(loop)
    runner.set_budget_profile("default")
    return runner, paths


def test_36_verified_actions_extend_without_context_explosion(tmp_path):
    runner, paths = prepare(tmp_path, 36)
    tracemalloc.start()
    try:
        result = runner.start("Leia os 36 arquivos do experimento e resuma.")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.response.speech_output == "Resumo verificável"
    assert len(runner.steps) == 36
    assert all(step["ok"] and step["verified"] is True for step in runner.steps)
    assert runner.max_actions == 36
    assert len(runner._planning_history()[-1]["content"]) <= 4300
    assert peak < 64 * 1024 * 1024
    assert all(path.exists() for path in paths)


def test_global_action_ceiling_blocks_49th_effect(tmp_path):
    runner, paths = prepare(tmp_path, 49)
    result = runner.start("Leia todos os arquivos necessários")
    assert len(runner.steps) == 48
    assert runner.max_actions == runner.AUTO_ACTION_CEILING
    assert not runner.active
    assert "Limite geral" in result.response.speech_output
    assert paths[-1].exists()
    assert runner.steps[-1]["params"]["path"] == str(paths[-2])
