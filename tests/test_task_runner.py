import copy
import json
from pathlib import Path

import pytest

from audit.logger import AuditLogger
from config import PermissionMode
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def reply(tool="none", params=None, speech="Pronto"):
    return json.dumps({"reasoning": "test", "alternative_suggestion": None, "emotion": "talk",
                       "action": {"type": tool, "params": params or {}}, "requires_confirmation": False,
                       "confirmation_prompt": None, "speech_output": speech})


def make_runner(tmp_path, responses, **kwargs):
    registry = ToolRegistry()
    loop = AgentLoop(OfflineLLM(responses), registry, AuditLogger(tmp_path / "logs", session_id="task-test"))
    runner = TaskRunner(loop, **kwargs)
    return runner, loop, registry


def test_task_catalog_reaches_model_and_internal_typeerror_is_not_retried(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [])
    registry.register(ToolSpec("read_file", "Read a file"), lambda p: ToolResult(True, "ok"))
    calls = []
    class Broken:
        def generate(self, prompt, history=None, memory_context=None, task_tools=None):
            calls.append(task_tools)
            raise TypeError("internal model error")
    loop.llm = Broken()
    result = runner.start("Leia")
    assert calls == [[{"name": "read_file", "description": "Read a file"}]]
    assert "internal model error" in result.response.speech_output
    assert not runner.active


def test_planner_retains_all_six_steps_including_first_failure(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [])
    histories = []
    def generate(prompt, history=None, **kwargs):
        histories.append(history)
        n = len(histories)
        return reply("read_file", {"path": str(n)}) if n <= 6 else reply()
    loop.llm.generate = generate
    registry.register(ToolSpec("read_file", "read"),
                      lambda p: ToolResult(p["path"] != "1", output="value-" + p["path"], error="first failed"))
    runner.start("Leia seis arquivos")
    ledger = json.loads(histories[-1][-1]["content"].split("\n", 1)[1])
    assert len(ledger) == 6
    assert ledger[0]["ok"] is False and ledger[0]["output"] == "first failed"
    assert ledger[-1]["output"] == "value-6"


def test_planning_ledger_is_bounded_and_marks_truncation(tmp_path):
    runner, loop, _ = make_runner(tmp_path, [])
    loop.history = [{"role": "user", "content": "x" * 10000}] * 20
    runner.steps = [{"tool": "read_file", "params": {"path": "p" * 8000},
                     "ok": True, "verified": True, "output": "a" * 1600,
                     "output_truncated": True} for _ in range(12)]
    history = runner._planning_history()
    assert sum(len(item["content"]) for item in history) < 6500
    ledger = json.loads(history[-1]["content"].split("\n", 1)[1])
    assert len(ledger) == 12
    assert all(item["output_truncated"] and item["params_truncated"] for item in ledger)


def test_two_real_files_then_answer_with_observations(tmp_path):
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_text("alpha")
    second.write_text("beta")
    runner, loop, registry = make_runner(tmp_path, [reply("read_file", {"path": str(first)}),
                                                  reply("read_file", {"path": str(second)}), reply(speech="alpha e beta")])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, output=Path(p["path"]).read_text()))
    progress = []
    result = runner.start("Leia os dois arquivos", progress.append)
    assert result.response.speech_output == "alpha e beta"
    assert len(runner.steps) == 2 and not runner.active
    assert [s["output"] for s in runner.steps] == ["alpha", "beta"]
    assert [p["phase"] for p in progress].count("observed") == 2
    assert len(loop.history) == 2  # One user request, no fabricated intermediate user turns.


def test_confirmation_resumes_and_second_action_needs_its_own_approval(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [reply("shell", {"n": 1}), reply("shell", {"n": 2}), reply()])
    loop.mode = PermissionMode.AUTONOMA
    calls = []
    registry.register(ToolSpec("shell", "destructive", destructive=True), lambda p: (calls.append(p) or ToolResult(True, "ok")))
    first = runner.start("Duas ações")
    assert first.needs_confirmation and calls == []
    second = runner.resume(first.pending_action, True)
    assert second.needs_confirmation and calls == [{"n": 1}]
    final = runner.resume(second.pending_action, False)
    assert not final.executed and not runner.active
    assert calls == [{"n": 1}]


def test_pending_action_cannot_be_changed_or_replayed(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("write_file", {"path": "original"})])
    calls = []
    registry.register(ToolSpec("write_file", "write", sensitive=True), lambda p: calls.append(p))
    pending = runner.start("Grave arquivo").pending_action
    tampered = copy.deepcopy(pending)
    tampered["params"]["path"] = "different"
    result = runner.resume(tampered, True)
    assert "não corresponde" in result.response.speech_output and calls == []
    with pytest.raises(ValueError):
        runner.resume(pending, True)


def test_repeat_is_blocked_before_second_execution(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"path": "same"})] * 2)
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: (calls.append(p) or ToolResult(True, "result")))
    result = runner.start("Leia")
    assert len(calls) == 1
    assert "repetição" in result.response.speech_output


def test_read_modify_read_is_allowed_for_verification(tmp_path):
    path = tmp_path / "config.txt"
    path.write_text("before")
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"path": str(path)}),
                                               reply("write_file", {"path": str(path), "content": "after"}),
                                               reply("read_file", {"path": str(path)}), reply()])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, Path(p["path"]).read_text()))

    def write(p):
        Path(p["path"]).write_text(p["content"])
        return ToolResult(True, "written")

    registry.register(ToolSpec("write_file", "write", sensitive=True), write)
    pending = runner.start("Atualize e confira o arquivo")
    assert pending.needs_confirmation
    runner.resume(pending.pending_action, True)
    assert [step["output"] for step in runner.steps] == ["before", "written", "after"]


def test_action_budget_and_deadline_block_effects(tmp_path):
    now = [0]
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"n": 1}), reply("read_file", {"n": 2})], max_actions=1, clock=lambda: now[0])
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: (calls.append(p) or ToolResult(True, "data")))
    assert "Limite" in runner.start("Leia duas vezes").response.speech_output
    assert len(calls) == 1


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_cancel_or_timeout_during_generation_prevents_next_tool(tmp_path, stop):
    now = [0]
    runner, loop, registry = make_runner(tmp_path, [], clock=lambda: now[0])
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: calls.append(p))

    def generate(*args, **kwargs):
        if stop == "cancel":
            runner.cancel()
        else:
            now[0] = 181
        return reply("read_file")

    loop.llm.generate = generate
    assert not runner.start("Leia").executed
    assert calls == [] and not runner.active


def test_cancel_while_waiting_for_confirmation_prevents_approved_effect(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("write_file")])
    calls = []
    registry.register(ToolSpec("write_file", "write", sensitive=True), lambda p: calls.append(p))
    pending = runner.start("Grave").pending_action
    runner.cancel()
    assert not runner.resume(pending, True).executed
    assert calls == []


def test_failed_tools_are_presented_as_failed_in_final_answer(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("read_file"), reply(speech="Fim")])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(False, error="missing"))
    result = runner.start("Leia")
    assert runner.steps[0]["ok"] is False
    assert "sem sucesso" in result.response.speech_output


def test_invalid_json_stops_without_side_effects(tmp_path):
    runner, _, _ = make_runner(tmp_path, ["invalid"])
    result = runner.start("Pedido")
    assert not result.response.parse_ok and not runner.active and runner.steps == []


def test_verifier_crash_preserves_uncertainty_about_started_action(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [reply("read_file")])
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: (calls.append(p) or ToolResult(True, "data")))

    def crash(*args):
        raise RuntimeError("verification unavailable")

    loop.verifier.verify = crash
    result = runner.start("Leia")
    assert len(calls) == 1
    assert "resultado não foi confirmado" in result.response.speech_output
