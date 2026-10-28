"""Recovery regenerates an unexecuted proposal; it never repairs action bytes."""

import json

import pytest

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import BackendUnavailable, ModelOutputError, OllamaClient, parse_response
from core.recovering_llm import RecoveringLLM
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def response(tool="none", params=None):
    return json.dumps({"reasoning": "Verificar o resultado.", "alternative_suggestion": None,
                      "emotion": "talk", "action": {"type": tool, "params": params or {}},
                      "requires_confirmation": False, "confirmation_prompt": None,
                      "speech_output": "Resposta verificada."})


def install(monkeypatch, outputs):
    calls = []
    pending = iter(outputs)

    def post(url, payload, timeout):
        calls.append((payload, timeout))
        return next(pending)

    monkeypatch.setattr("core.runtime_budget.post_ollama_json", post)
    return calls


def output(raw, reason="stop"):
    return {"message": {"content": raw}, "done": True, "done_reason": reason, "eval_count": 512}


def loop_for(tmp_path, client):
    return AgentLoop(client, ToolRegistry(), AuditLogger(tmp_path / "audit"))


def test_truncated_media_status_regenerates_once_with_same_tools(monkeypatch):
    # Same failure shape as the reported Spotify response: ends inside action.
    truncated = '{"action":{"type":"browser","params":{"action":"media_status"}'
    calls = install(monkeypatch, [output(truncated, "length"), output(response("browser", {"action": "media_status"}))])
    client = OllamaClient()
    result = parse_response(client.generate("Verifique a reprodução", task_tools=[{"name": "browser"}]))
    assert result.parse_ok and result.action.params == {"action": "media_status"}
    assert len(calls) == 2
    assert [c[0]["options"]["num_predict"] for c in calls] == [512, 1024]
    assert calls[1][0]["options"]["temperature"] == 0
    assert calls[0][0]["format"] == calls[1][0]["format"]
    assert calls[1][1] <= calls[0][1]
    assert truncated not in str(calls[1][0]["messages"])
    assert [r["valid_json"] for r in client.generation_report] == [False, True]


def test_recovered_write_still_requires_confirmation(tmp_path, monkeypatch):
    install(monkeypatch, [output('{"action":', "length"), output(response("write_file", {"path": "owned.txt", "content": "hello"}))])
    loop = loop_for(tmp_path, OllamaClient())
    effects = []
    loop.registry.register(ToolSpec("write_file", "write", sensitive=True), lambda p: effects.append(p))
    progress = []
    result = TaskRunner(loop).start("Grave hello em owned.txt", on_progress=progress.append)
    assert result.needs_confirmation and not result.executed and not effects
    assert result.pending_action["params"]["content"] == "hello"
    reports = [e for e in loop.audit.read_all() if e["event"] == "model_generation"]
    assert len(reports[0]["attempts"]) == 2
    assert [p["phase"] for p in progress] == ["planning", "recovering", "confirmation"]


@pytest.mark.parametrize("raw", ['{"action":', response("write_file")])
def test_exhausted_recovery_never_executes_even_closed_json_marked_truncated(tmp_path, monkeypatch, raw):
    calls = install(monkeypatch, [output(raw, "length"), output(raw, "length")])
    client = OllamaClient()
    recovering = RecoveringLLM(client, lambda: pytest.fail("Must not replace model"))
    loop = loop_for(tmp_path, recovering)
    effects = []
    loop.registry.register(ToolSpec("write_file", "write"), lambda p: effects.append(p))
    result = loop.process("Grave")
    assert not result.executed and not result.response.parse_ok and not effects
    assert result.response.action.type == "none" and len(calls) == 2
    assert "json.loads" not in result.response.speech_output
    assert recovering._client is client and not recovering.unavailable_reason


def test_failed_recovery_preserves_completed_steps_without_replaying(tmp_path, monkeypatch):
    calls = install(monkeypatch, [output(response("read_file")), output('{"action":', "length"), output("invalid")])
    loop = loop_for(tmp_path, OllamaClient())
    effects = []
    loop.registry.register(ToolSpec("read_file", "read"), lambda p: effects.append(p) or ToolResult(True, "data"))
    runner = TaskRunner(loop)
    result = runner.start("Leia e resuma")
    assert len(effects) == len(runner.steps) == 1
    assert not result.response.parse_ok and not runner.active and len(calls) == 3
    assert loop.audit.read_all()[-1]["state"] == "invalid_response"


def test_explicit_token_budget_and_custom_schema_are_preserved(monkeypatch):
    calls = install(monkeypatch, [output('{"code":', "length"), output('{"code":"x"}')])
    schema = {"type": "object", "properties": {"code": {"type": "string"}}}
    assert json.loads(OllamaClient().generate("Código", schema=schema, max_output_tokens=64)) == {"code": "x"}
    assert all(c[0]["options"]["num_predict"] == 64 and c[0]["format"] == schema for c in calls)


def test_no_retry_on_network_error(monkeypatch):
    calls = []
    def fail(*args):
        calls.append(args)
        raise OSError("offline")
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", fail)
    with pytest.raises(BackendUnavailable):
        OllamaClient().generate("Oi")
    assert len(calls) == 1


def test_retry_cannot_start_after_generation_deadline(monkeypatch):
    now, calls = [0], []
    monkeypatch.setattr("core.llm_client.time.monotonic", lambda: now[0])
    def post(*args):
        calls.append(args)
        now[0] = 121
        return output("invalid")
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", post)
    with pytest.raises(ModelOutputError, match="Prazo"):
        OllamaClient(timeout=120).generate("Oi")
    assert len(calls) == 1


def test_cancel_between_attempts_prevents_second_inference_and_keeps_model(tmp_path, monkeypatch):
    from core import runtime_budget
    actual = runtime_budget.post_ollama_json
    client = OllamaClient()
    loop = loop_for(tmp_path, RecoveringLLM(client, lambda: client))
    runner = TaskRunner(loop)
    calls = []
    def post(*args):
        calls.append(args)
        if len(calls) == 1:
            runner.cancel()
            return output("invalid")
        return actual(*args)  # cancellation must reject before any network/telemetry
    monkeypatch.setattr(runtime_budget, "post_ollama_json", post)
    monkeypatch.setattr(runtime_budget, "resource_snapshot", lambda: pytest.fail("Inference admitted after cancel"))
    runner.start("Leia")
    assert runner.steps == [] and not runner.active
    assert loop.llm._client is client


def test_internal_type_error_is_not_replayed_by_agent_loop(tmp_path):
    calls = []
    class Broken:
        def generate(self, *args, **kwargs):
            calls.append(True)
            raise TypeError("internal")
    with pytest.raises(TypeError):
        loop_for(tmp_path, Broken()).process("Oi")
    assert len(calls) == 1


@pytest.mark.parametrize("raw", [None, '{"action":{},"action":{}}',
                                  response("read_file", {"value": float("nan")}), "[" * 2000,
                                  response().replace('"reasoning":', '"reasoning:":"ambiguous","reasoning":'),
                                  response().replace('"type":', '"type:":"read_file","type":'),
                                  response("read_file").replace('"params": {}', '"params": []'),
                                  response("read_file", {"number": 1.5}).replace("1.5", "1e999")])
def test_ambiguous_or_nontext_json_is_rejected_without_exception(raw):
    parsed = parse_response(raw)
    assert not parsed.parse_ok and parsed.action.type == "none"
