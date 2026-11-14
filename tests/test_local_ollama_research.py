"""No-network tests exercising the real TaskRunner and disposable file tools."""
import importlib.util
import json
from pathlib import Path

import pytest

from core.llm_client import OfflineLLM, OllamaClient


SPEC = importlib.util.spec_from_file_location(
    "nyx_benchmark_module", Path(__file__).resolve().parents[1] / "tools" / "benchmark_local_nyx.py"
)
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


def response(tool="none", params=None, speech="Pronto"):
    return json.dumps({"emotion": "idle", "speech_output": speech,
                       "action": {"type": tool, "params": params or {}},
                       "requires_confirmation": False})


def test_plan_is_inert_and_requires_explicit_run(monkeypatch, capsys):
    def fail(*_):
        raise AssertionError("plan must not call network or sample RAM")
    monkeypatch.setattr(bench, "host_memory_sample", fail)
    assert bench.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PLAN_ONLY"
    assert payload["network_requests"] == 0
    assert payload["tasks_if_run"] == 4


def test_live_mode_requires_exact_existing_model(monkeypatch):
    monkeypatch.setattr(bench, "host_memory_sample", lambda: (4 * 1024**3, 0))
    class FakeOllama:
        def __init__(self, **kwargs):
            pass
        def is_available(self):
            return True
        def list_models(self):
            return ["qwen2.5:3b-instruct"]
    monkeypatch.setattr(bench, "OllamaClient", FakeOllama)
    with pytest.raises(RuntimeError, match="não instalado"):
        bench.run_experiment(model_name="other-model:latest", repeats=1, timeout=20, seed=42)


def test_approved_exact_write_is_independently_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "_gpu_free_mib", lambda: None)
    root = tmp_path / "case"
    p = root / "answer.txt"
    fixture = bench.SCENARIOS[0]
    model = OfflineLLM([
        response("write_file", {"path": str(p), "content": fixture["content"]}),
        response(speech="Gravei o arquivo"),
    ])
    trial = bench.run_trial(root, fixture, variant="goal_gate", model=model, timeout=20, repeat=0)
    assert trial["verified"] is True
    assert trial["reason"] == "exact_sha256"
    assert trial["approvals"] == 1 and trial["denials"] == 0
    assert p.read_text(encoding="utf-8") == fixture["content"]
    assert trial["resources"]["vram_peak_measured"] is False


def test_two_step_read_then_write_with_same_model_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "_gpu_free_mib", lambda: None)
    root = tmp_path / "case"
    fixture = bench.SCENARIOS[1]
    out = root / "answer.txt"
    source = root / fixture["source"]
    model = OfflineLLM([
        response("read_file", {"path": str(source)}),
        response("write_file", {"path": str(out), "content": fixture["content"]}),
        response(speech="Copiado"),
    ])
    trial = bench.run_trial(root, fixture, variant="baseline", model=model, timeout=20, repeat=0)
    assert trial["verified"] is True
    assert trial["actions"] == 2
    assert trial["approvals"] == 1
    assert source.read_text() == out.read_text()


def test_unsafe_payload_denied_even_with_model_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "_gpu_free_mib", lambda: None)
    root = tmp_path / "case"
    malicious = tmp_path / "elsewhere.txt"
    model = OfflineLLM([
        response("write_file", {"path": str(malicious), "content": "not authorized"}),
    ])
    trial = bench.run_trial(root, bench.SCENARIOS[0],
                            variant="goal_gate", model=model, timeout=20, repeat=0)
    assert trial["verified"] is False
    assert trial["denials"] == 1
    assert trial["approvals"] == 0
    assert not malicious.exists()


def test_model_seed_validation_never_starts_network():
    with pytest.raises(ValueError):
        OllamaClient(seed=True)
    with pytest.raises(ValueError):
        OllamaClient(seed=-1)
    assert OllamaClient(seed=42).seed == 42
    assert OllamaClient().seed is None
