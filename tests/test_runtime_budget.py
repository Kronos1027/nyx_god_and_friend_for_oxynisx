import threading
import time

import pytest

from core.runtime_budget import (
    GIB,
    InferenceBusyError,
    InferenceGate,
    InferencePressureError,
    ResourceSnapshot,
    ensure_resource_headroom,
    model_weight_budget_bytes,
    safe_context_tokens,
    admit_gguf_load,
)


@pytest.mark.parametrize(
    ("ram", "vram", "expected"),
    [
        (2 * GIB, 10 * GIB, 1024),
        (5 * GIB, 10 * GIB, 2048),
        (16 * GIB, 4 * GIB, 2048),
        (16 * GIB, 10 * GIB, 4096),
        (16 * GIB, None, 4096),
    ],
)
def test_context_budget_shrinks_under_memory_pressure(ram, vram, expected):
    snapshot = ResourceSnapshot(ram, 12 * GIB if vram is not None else None, vram)
    assert safe_context_tokens(snapshot) == expected


def test_model_weight_budget_reserves_host_and_display_memory():
    snapshot = ResourceSnapshot(16 * GIB, 12 * GIB, 10 * GIB)
    assert model_weight_budget_bytes(snapshot) == 6 * GIB


def test_cuda_router_reserves_staging_ram_without_counting_all_gpu_weights_twice():
    snapshot = ResourceSnapshot(4 * GIB, 12 * GIB, 10 * GIB)
    assert model_weight_budget_bytes(snapshot) == 4 * GIB


def test_gguf_cannot_bypass_empty_model_budget(tmp_path, monkeypatch):
    from core import runtime_budget

    model = tmp_path / "example.gguf"
    model.write_bytes(b"GGUF")
    monkeypatch.setattr(runtime_budget, "resource_snapshot", lambda: ResourceSnapshot(2 * GIB, 12 * GIB, 10 * GIB))
    with pytest.raises(InferencePressureError, match="não cabe"):
        admit_gguf_load(model, 8192)


def test_unavailable_ollama_does_not_load_unbudgeted_legacy_model(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from core import runtime_budget
    from core.llm_client import OllamaClient, OfflineLLM, create_llm_client, parse_response

    model = tmp_path / "example.gguf"
    model.write_bytes(b"GGUF")
    monkeypatch.setattr(runtime_budget, "resource_snapshot", lambda: ResourceSnapshot(2 * GIB, 12 * GIB, 10 * GIB))
    monkeypatch.setattr(OllamaClient, "is_available", lambda self: False)
    config = SimpleNamespace(model_path=model, grammar_path=Path("src/core/schema.gbnf"), n_gpu_layers=-1, n_ctx=8192)
    client, backend = create_llm_client(cfg=config)
    assert isinstance(client, OfflineLLM)
    assert backend == "offline_fallback"
    assert "sem modelo de linguagem ativo" in parse_response(client.generate("olá")).speech_output


def test_inference_gate_admits_one_active_and_bounds_waiters():
    gate = InferenceGate(max_waiters=1)
    timed_out = []

    def wait_for_slot():
        try:
            with gate.slot(timeout=0.05):
                pass
        except InferenceBusyError:
            timed_out.append(True)

    with gate.slot():
        waiter = threading.Thread(target=wait_for_slot)
        waiter.start()
        deadline = time.monotonic() + 1
        while not gate._queue and time.monotonic() < deadline:
            time.sleep(0.001)
        with pytest.raises(InferenceBusyError, match="cheia"):
            with gate.slot(timeout=0.01):
                pass
        waiter.join(timeout=2)
        assert not waiter.is_alive()

    waiter.join(timeout=1)
    assert not waiter.is_alive()
    assert timed_out == [True]


@pytest.mark.parametrize(
    ("ram", "vram", "message"),
    [
        (GIB - 1, 10 * GIB, "RAM"),
        (16 * GIB, 700 * 1024 * 1024, "VRAM"),
    ],
)
def test_inference_is_rejected_at_critical_memory_pressure(ram, vram, message):
    snapshot = ResourceSnapshot(ram, 12 * GIB, vram)
    with pytest.raises(InferencePressureError, match=message):
        ensure_resource_headroom(snapshot)
