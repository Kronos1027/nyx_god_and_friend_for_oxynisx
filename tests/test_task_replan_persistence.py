"""Crash/resume checkpoints must preserve the bounded final-delivery retry."""
import json

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_journal import TaskJournal
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def reply():
    return json.dumps({"emotion": "idle", "speech_output": "Feito",
                       "action": {"type": "none", "params": {}},
                       "requires_confirmation": False})


def make(tmp_path, journal, model):
    registry = ToolRegistry()
    registry.register(ToolSpec("ui_action", "UI test"), lambda p: ToolResult(True, "mock"))
    loop = AgentLoop(model, registry, AuditLogger(tmp_path / "logs"))
    runner = TaskRunner(loop, journal=journal)
    runner.set_budget_profile("default")
    return runner, loop


def test_delivery_replan_durable_across_pause_and_restart(tmp_path):
    path = tmp_path / "tasks.db"
    first_journal = TaskJournal(path)
    runner, loop = make(tmp_path / "first", first_journal, OfflineLLM([]))

    class PauseDuringSecondGeneration:
        def __init__(self):
            self.calls = 0
        def generate(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 2:
                runner.pause()
            return reply()

    model = PauseDuringSecondGeneration()
    loop.llm = model
    result = runner.start("Abra um aplicativo")
    assert not result.executed
    assert runner.delivery_replans == 1 and model.calls == 2
    task_id = runner.task_id
    saved = first_journal.get(task_id)
    assert saved["state"] == "PAUSED"
    assert saved["delivery_replans"] == 1
    first_journal.close()

    second_journal = TaskJournal(path)
    next_model = OfflineLLM([reply()])
    resumed, _ = make(tmp_path / "second", second_journal, next_model)
    output = resumed.continue_task(task_id)
    assert resumed.delivery_replans == 1
    assert len(next_model.received) == 1
    assert "não foi comprovada" in output.response.speech_output
    assert second_journal.get(task_id)["state"] == "PLANNING_FINISHED"
    second_journal.close()
