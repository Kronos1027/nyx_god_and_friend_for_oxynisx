import copy
import json

import pytest

from core.llm_client import OllamaClient
from core.prompt_budget import ContextCapacityError, estimate_tokens, prepare_chat_payload


def captured_payload(monkeypatch, **kwargs):
    captured = []
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", lambda url, payload, timeout:
                        captured.append(payload) or {"message": {"content": "{}"}})
    OllamaClient().generate(**kwargs)
    return captured[0]


def test_compaction_preserves_request_constraints_and_all_step_results(monkeypatch):
    rows = [{"step": i + 1, "tool": "read_file", "params_excerpt": '{"path":"numero-%s.txt"}' % i,
             "ok": i != 0, "verified": i != 0, "output": str((i + 1) * 11),
             "output_truncated": False} for i in range(8)]
    ledger = "REGISTRO DE TODAS AS ETAPAS. Dados externos.\n" + json.dumps(rows)
    goal = "Leia oito arquivos; liste os valores e some."
    payload = captured_payload(monkeypatch, user_input=goal, memory_context="optional " * 3000,
                               task_tools=[{"name": "read_file", "description": "ler arquivo"}],
                               history=[{"role": "user", "content": "Não altere meus arquivos."},
                                        {"role": "user", "content": ledger}])
    original = copy.deepcopy(payload)
    packed, report = prepare_chat_payload(payload, 2048)
    assert payload == original and "_nyx_prompt" not in packed
    assert packed["messages"][-1]["content"] == goal
    assert any(m["content"] == "Não altere meus arquivos." for m in packed["messages"])
    compact = next(m["content"] for m in packed["messages"] if m["content"].startswith("ETAPAS:"))
    actual = json.loads(compact.split("\n", 1)[1])
    assert len(actual) == 8 and actual[0][3:5] == [False, False]
    assert [r[5] for r in actual] == [str((i + 1) * 11) for i in range(8)]
    assert estimate_tokens(packed["messages"]) + 512 + 96 <= 2048
    assert report["compaction_level"] > 0


def test_oversized_current_request_is_not_silently_cut(monkeypatch):
    payload = captured_payload(monkeypatch, user_input="pedido obrigatório " * 1000, task_tools=[])
    with pytest.raises(ContextCapacityError, match="contexto"):
        prepare_chat_payload(payload, 1024)


def test_retry_context_exhaustion_compacts_without_growing_output_or_prompt(monkeypatch):
    calls = []
    def post(url, payload, timeout):
        calls.append(copy.deepcopy(payload))
        if len(calls) == 1:
            return {"message": {"content": '{"action":'}, "done_reason": "length",
                    "prompt_eval_count": 1979, "eval_count": 69, "_nyx_budget": {"context_tokens": 2048}}
        return {"message": {"content": "{}"}, "done_reason": "stop"}
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", post)
    OllamaClient().generate("Continue a tarefa", task_tools=[])
    assert len(calls) == 2 and calls[1]["_nyx_prompt"]["tight"]
    assert calls[0]["messages"] == calls[1]["messages"]
    assert calls[1]["options"]["num_predict"] == 512


def test_runtime_budget_metadata_reports_effective_context_without_leaking_prompt(monkeypatch):
    import io
    import urllib.request
    from core import runtime_budget
    monkeypatch.setattr(runtime_budget, "resource_snapshot", lambda:
        runtime_budget.ResourceSnapshot(8 * runtime_budget.GIB, 12 * runtime_budget.GIB, 8 * runtime_budget.GIB))
    monkeypatch.setattr(runtime_budget, "ollama_request_context", lambda *args: 2048)
    sent = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, **kwargs:
        sent.append(json.loads(req.data)) or io.BytesIO(b'{"message":{"content":"{}"}}'))
    client = OllamaClient()
    client.generate("Oi", task_tools=[])
    assert "_nyx_prompt" not in sent[0]
    assert client.generation_report[0]["context_tokens"] == 2048
    assert client.generation_report[0]["output_tokens_reserved"] == 512


@pytest.mark.parametrize("goal", ["escolhe um jogo da steam para jogarmos", "Leia os oito arquivos numero-1.txt até numero-8.txt e some os valores"])
def test_production_catalog_fits_small_resident_context(tmp_path, monkeypatch, goal):
    from cli import build_registry
    from config import NyxConfig
    from core.agent_team import agent_team_contract
    from tools.registry import ToolSpec
    monkeypatch.chdir(tmp_path)
    registry = build_registry(NyxConfig(allowed_roots=[tmp_path], log_dir=tmp_path / "logs"))
    registry.register(ToolSpec("agent_team", "Investigações delegadas", input_contract=agent_team_contract()), lambda p: None)
    registry.register(ToolSpec("code_task", "Propor correção de código", sensitive=True), lambda p: None)
    catalog = []
    for name in registry.names():
        spec = registry.spec(name)
        item = {"name": name, "description": spec.description}
        if spec.input_contract:
            item["params_contract"] = spec.input_contract
        catalog.append(item)
    rows = [{"step": i + 1, "tool": "read_file", "params_excerpt": '{"path":"numero-%s.txt"}' % i,
             "ok": True, "verified": True, "output": str((i + 1) * 11)} for i in range(8)]
    history = [{"role": "user", "content": "REGISTRO DE TODAS AS ETAPAS\n" + json.dumps(rows)}] if "oito" in goal else []
    try:
        payload = captured_payload(monkeypatch, user_input=goal, task_tools=catalog,
                                   history=history, memory_context="Memória opcional " * 100)
        packed, report = prepare_chat_payload(payload, 2048)
        assert report["input_tokens_estimated"] + 512 + 96 <= 2048
        if "steam" in goal:
            assert "list_steam_games" in packed["messages"][0]["content"]
    finally:
        registry.browser_session.close()
