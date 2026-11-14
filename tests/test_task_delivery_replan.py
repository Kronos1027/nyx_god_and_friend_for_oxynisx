"""Avoid unbounded retries when the model claims an external task is done."""
import json

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_reliability import should_replan_premature_finish
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def response(tool="none", text="Feito", params=None):
    return json.dumps({"emotion": "idle", "speech_output": text,
                       "action": {"type": tool, "params": params or {}},
                       "requires_confirmation": False})


def make(tmp_path, llm):
    registry = ToolRegistry()
    loop = AgentLoop(llm, registry, AuditLogger(tmp_path / "logs"))
    runner = TaskRunner(loop)
    runner.set_budget_profile("default")  # GUI-like profile only
    return runner, registry, loop


def test_one_replan_when_no_tool_executed(tmp_path):
    model = OfflineLLM([response(), response()])
    runner, registry, loop = make(tmp_path, model)
    registry.register(ToolSpec("ui_action", "app tool"), lambda p: ToolResult(True, "ok"))
    result = runner.start("Abra um aplicativo")
    assert not runner.active
    assert runner.delivery_replans == 1
    assert "não foi comprovada" in result.response.speech_output
    events = [event for event in loop.audit.read_all() if event["event"] == "task_replan"]
    assert len(events) == 1
    assert events[0]["reason"] == "unverified_premature_completion"
    assert "nenhuma execução foi verificada" in model.received[-1]


def test_second_plan_can_choose_an_authorized_action(tmp_path):
    model = OfflineLLM([response(), response("read_file", "Vou ler", {"path": "example"}), response(text="Resumo")])
    runner, registry, _ = make(tmp_path, model)
    registry.register(ToolSpec("ui_action", "app tool"), lambda p: ToolResult(True, "ok"))
    registry.register(ToolSpec("read_file", "read-only"), lambda p: ToolResult(True, "conteúdo"))
    result = runner.start("Abra um aplicativo")
    assert runner.delivery_replans == 1
    assert len(runner.steps) == 1 and runner.steps[0]["tool"] == "read_file"
    assert result.response.parse_ok


def test_refusal_never_loops():
    assert not should_replan_premature_finish(
        "Abra app", [], action_type="none", speech="Não consigo acessar sua tela",
        tool_names=["ui_action"], attempts=0,
    )
    assert not should_replan_premature_finish(
        "Abra app", [], action_type="none", speech="Pronto",
        tool_names=["ui_action"], attempts=1,
    )
    assert not should_replan_premature_finish(
        "Abra app", [], action_type="none", speech="Pronto",
        tool_names=[], attempts=0,
    )
    assert not should_replan_premature_finish(
        "O que significa abrir uma janela?", [], action_type="none", speech="Pronto",
        tool_names=["ui_action"], attempts=0,
    )


def test_strict_profile_does_not_repeat_model_inference(tmp_path):
    registry = ToolRegistry()
    model = OfflineLLM([response()])
    loop = AgentLoop(model, registry, AuditLogger(tmp_path / "logs"))
    registry.register(ToolSpec("ui_action", "app"), lambda p: ToolResult(True, "ok"))
    runner = TaskRunner(loop)  # strict programmatic mode: no extra inference
    result = runner.start("Abra um aplicativo")
    assert runner.delivery_replans == 0
    assert len(model.received) == 1
    assert "não foi comprovada" in result.response.speech_output
