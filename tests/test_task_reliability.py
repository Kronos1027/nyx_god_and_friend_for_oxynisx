"""Task reliability regression: no fabricated completion or unsafe retry."""
from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_reliability import StepEvidence, trailing_failures, recovery_hint, completion_warning
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry, ToolResult, ToolSpec
import json


def reply(tool="none", params=None, text="Feito"):
    return json.dumps({
        "emotion": "idle", "action": {"type": tool, "params": params or {}},
        "speech_output": text, "requires_confirmation": False,
    })


def build(tmp_path, messages, **kwargs):
    registry = ToolRegistry()
    loop = AgentLoop(OfflineLLM(messages), registry, AuditLogger(tmp_path / "logs", session_id="r"))
    return TaskRunner(loop, **kwargs), loop, registry


def test_evidence_is_based_on_verification_not_success_flags():
    steps = [
        {"tool": "read_file", "ok": True, "verified": True},
        {"tool": "browser", "ok": True, "verified": None},
        {"tool": "shell", "ok": False, "verified": False},
        {"tool": "code_task", "ok": True, "verified": False},
    ]
    e = StepEvidence.inspect(steps)
    assert (e.attempted, e.succeeded, e.verified, e.failed, e.uncertain) == (4, 3, 1, 2, 1)
    assert e.has_verified_action


def test_stall_count_resets_after_verified_progress_or_tool_change():
    fail = {"tool": "read_file", "ok": False, "verified": False}
    good = {"tool": "read_file", "ok": True, "verified": True}
    other = {"tool": "find_files", "ok": False, "verified": False}
    assert trailing_failures([fail, fail, fail]) == 3
    assert trailing_failures([fail, good, fail]) == 1
    assert trailing_failures([fail, other]) == 1
    assert trailing_failures([]) == 0


def test_feedback_is_bounded_and_has_no_tool_error_leak():
    step = {"tool": "read_file", "output": "password=secret", "params": {"token": "secret"}}
    advice = recovery_hint(step)
    assert "caminho" in advice and "secret" not in advice and len(advice) < 450


def test_unexecuted_external_command_is_not_reported_verified(tmp_path):
    runner, _, _ = build(tmp_path, [reply(text="Aplicativo aberto")])
    result = runner.start("Abra o navegador")
    assert "não foi comprovada" in result.response.speech_output
    assert not runner.active and runner.steps == []


def test_normal_informational_answer_needs_no_tool(tmp_path):
    runner, _, _ = build(tmp_path, [reply(text="É uma biblioteca")])
    result = runner.start("O que é SQLite?")
    assert result.response.speech_output == "É uma biblioteca"


def test_failure_feedback_reaches_planner_before_next_choice(tmp_path):
    runner, loop, registry = build(tmp_path, [])
    prompts = []
    def generate(prompt, **kwargs):
        prompts.append(prompt)
        if len(prompts) == 1:
            return reply("read_file", {"path": "not_here"})
        if len(prompts) == 2:
            assert "não teve sucesso/verificação" in prompt
            assert "Confira o caminho" in prompt
            return reply("find_files", {"pattern": "*.txt"})
        return reply(text="Relatório: falta o arquivo solicitado")
    loop.llm.generate = generate
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(False, error="not found"))
    registry.register(ToolSpec("find_files", "find"), lambda p: ToolResult(True, "nenhum"))
    result = runner.start("Leia um arquivo que não existe")
    assert len(prompts) == 3
    assert len(runner.steps) == 2
    assert "sem sucesso" in result.response.speech_output


def test_three_consecutive_failures_with_same_tool_stop_before_fourth(tmp_path):
    runner, loop, registry = build(tmp_path, [])
    calls = []
    def generate(prompt, **kwargs):
        return reply("read_file", {"path": f"p{len(calls) + 1}"})
    loop.llm.generate = generate
    registry.register(ToolSpec("read_file", "read"), lambda p: (
        calls.append(p["path"]) or ToolResult(False, error="missing")
    ))
    result = runner.start("Leia um arquivo")
    assert calls == ["p1", "p2", "p3"]
    assert "Três tentativas consecutivas" in result.response.speech_output
    assert not runner.active


def test_verified_actions_avoid_false_no_execution_warning(tmp_path):
    runner, _, registry = build(tmp_path, [
        reply("read_file", {"path": "a"}), reply(text="Analisado")
    ])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, "ok"))
    result = runner.start("Abra e leia o arquivo")
    assert result.response.speech_output == "Analisado"
    assert StepEvidence.inspect(runner.steps).has_verified_action


def test_missing_or_invalid_parse_does_not_claim_success():
    assert completion_warning("Abra um aplicativo", [], parse_ok=False) == ""
    assert completion_warning("Abra um aplicativo", [], parse_ok=True)
    assert completion_warning("Explique como abrir um aplicativo", [], parse_ok=True) == ""
