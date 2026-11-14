"""Ollama residency fast-path must never circumvent RAM/VRAM checks."""
import pytest

from core import runtime_budget
from core.ollama_admission import should_probe_resident


GIB = runtime_budget.GIB
MODEL = {"name": "qwen:3b", "size": 2 * GIB, "digest": "sha256:valid"}
SAFE = runtime_budget.ResourceSnapshot(8 * GIB, 12 * GIB, 6 * GIB)


@pytest.mark.parametrize(("ram","vram","digest","expected"),[
    (8 * GIB, 6 * GIB, "sha256:valid", True),
    (GIB, 6 * GIB, "sha256:valid", False),
    (8 * GIB, 3 * GIB, "sha256:valid", False),
    (8 * GIB, None, "sha256:valid", False),
    (None, 8 * GIB, "sha256:valid", False),
    (8 * GIB, 8 * GIB, "", False),
])
def test_residency_precheck_only_enables_possible_residents(ram,vram,digest,expected):
    snap = runtime_budget.ResourceSnapshot(ram, 12 * GIB, vram)
    assert should_probe_resident(snap, {"digest": digest}) is expected


def test_cpu_only_context_saves_one_ps_request_without_guessing_model_size(monkeypatch):
    calls = []
    def inventory(host, endpoint):
        calls.append(endpoint)
        if endpoint == "tags":
            return [MODEL]
        raise AssertionError("/ps cannot yield a GPU-resident model on CPU-only host")
    monkeypatch.setattr(runtime_budget, "ollama_models", inventory)
    snap = runtime_budget.ResourceSnapshot(8 * GIB, None, None)
    assert runtime_budget.ollama_request_context("http://127.0.0.1:11434", "qwen:3b", snap) == 4096
    assert calls == ["tags"]


def test_low_vram_never_reuses_resident_and_still_enforces_weight_limit(monkeypatch):
    calls = []
    def inventory(host, endpoint):
        calls.append(endpoint)
        return [MODEL]
    monkeypatch.setattr(runtime_budget, "ollama_models", inventory)
    snap = runtime_budget.ResourceSnapshot(8 * GIB, 12 * GIB, GIB)
    with pytest.raises(runtime_budget.InferencePressureError, match="orçamento"):
        runtime_budget.ollama_request_context("http://localhost:11434", "qwen:3b", snap)
    assert calls == ["tags"]


def test_eligible_gpu_checks_fresh_resident_and_reuses_context(monkeypatch):
    calls = []
    def inventory(host, endpoint):
        calls.append(endpoint)
        if endpoint == "tags":
            return [MODEL]
        return [{
            **MODEL, "size_vram": MODEL["size"],
            "context_length": 2048,
        }]
    monkeypatch.setattr(runtime_budget, "ollama_models", inventory)
    assert runtime_budget.ollama_request_context("http://localhost:11434", "qwen:3b", SAFE) == 2048
    assert calls == ["tags", "ps"]


def test_eligible_gpu_cold_model_still_checked_for_weight_budget(monkeypatch):
    calls = []
    def inventory(host, endpoint):
        calls.append(endpoint)
        return [MODEL] if endpoint == "tags" else []
    monkeypatch.setattr(runtime_budget, "ollama_models", inventory)
    assert runtime_budget.ollama_request_context("http://localhost:11434", "qwen:3b", SAFE) == 4096
    assert calls == ["tags", "ps"]


def test_unverified_model_cannot_be_admitted_even_if_resident(monkeypatch):
    calls = []
    def inventory(host, endpoint):
        calls.append(endpoint)
        return [MODEL] if endpoint == "tags" else []
    monkeypatch.setattr(runtime_budget, "ollama_models", inventory)
    with pytest.raises(runtime_budget.InferencePressureError):
        runtime_budget.ollama_request_context("http://localhost:11434", "uninstalled:13b", SAFE)
    assert calls == ["tags"]
