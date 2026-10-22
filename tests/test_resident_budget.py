import io
import json

import pytest

from core import runtime_budget as budget


INSTALLED = {"name": "example:4b", "digest": "same-digest", "size": 3 * budget.GIB}
RUNNING = {**INSTALLED, "size_vram": 3 * budget.GIB, "context_length": 2048}
SNAPSHOT = budget.ResourceSnapshot(3 * budget.GIB, 12 * budget.GIB, 5 * budget.GIB)


def test_resident_reuse_does_not_count_weights_twice():
    assert budget.model_weight_budget_bytes(SNAPSHOT) < INSTALLED["size"]
    assert budget.resident_context(SNAPSHOT, INSTALLED, [RUNNING]) == 2048


@pytest.mark.parametrize("change", [
    {"digest": "different"}, {"name": "other:4b"}, {"size_vram": budget.GIB},
    {"context_length": 4096}, {"context_length": True}, {"size": -1},
    {"size_vram": None}, {"context_length": 0},
])
def test_incompatible_resident_is_not_credited(change):
    assert budget.resident_context(SNAPSHOT, INSTALLED, [{**RUNNING, **change}]) is None


@pytest.mark.parametrize("snapshot", [
    budget.ResourceSnapshot(budget.GIB, 12 * budget.GIB, 5 * budget.GIB),
    budget.ResourceSnapshot(3 * budget.GIB, 12 * budget.GIB, 3 * budget.GIB),
    budget.ResourceSnapshot(None, None, None),
])
def test_resident_still_requires_system_reserves(snapshot):
    assert budget.resident_context(snapshot, INSTALLED, [RUNNING]) is None


def test_expired_resident_cannot_bypass_load_budget(monkeypatch):
    running = [RUNNING]
    monkeypatch.setattr(budget, "ollama_models", lambda host, endpoint: [INSTALLED] if endpoint == "tags" else running)
    assert budget.ollama_request_context("http://localhost:11434", INSTALLED["name"], SNAPSHOT) == 2048
    running.clear()
    with pytest.raises(budget.InferencePressureError):
        budget.ollama_request_context("http://localhost:11434", INSTALLED["name"], SNAPSHOT)


def test_existing_context_is_preserved_in_post(monkeypatch):
    import urllib.request
    captured = []
    monkeypatch.setattr(budget, "resource_snapshot", lambda: budget.ResourceSnapshot(8 * budget.GIB, 12 * budget.GIB, 6 * budget.GIB))
    monkeypatch.setattr(budget, "ollama_models", lambda host, endpoint: [INSTALLED] if endpoint == "tags" else [RUNNING])
    def send(request, timeout):
        captured.append(json.loads(request.data))
        return io.BytesIO(b'{}')
    monkeypatch.setattr(urllib.request, "urlopen", send)
    payload = {"model": INSTALLED["name"], "options": {"num_ctx": 4096}}
    budget.post_ollama_json("http://localhost:11434/api/chat", payload, 10)
    assert captured[0]["options"]["num_ctx"] == 2048
    assert payload["options"]["num_ctx"] == 4096


def test_failed_admission_never_posts_and_releases_queue(monkeypatch):
    import urllib.request
    monkeypatch.setattr(budget, "resource_snapshot", lambda: SNAPSHOT)
    monkeypatch.setattr(budget, "ollama_models", lambda host, endpoint: [INSTALLED] if endpoint == "tags" else [])
    def unexpected_request(*args, **kwargs):
        pytest.fail("A refused model must not receive a generation request")
    monkeypatch.setattr(urllib.request, "urlopen", unexpected_request)
    with pytest.raises(budget.InferencePressureError):
        budget.post_ollama_json("http://localhost:11434/api/chat", {"model": INSTALLED["name"]}, 10)
    assert budget.INFERENCE_GATE.telemetry()["active"] == 0


@pytest.mark.parametrize("raw", [b'[]', b'null', b'{', b'{"models":null}', b'x' * 1_048_577], ids=["array", "null", "partial", "null-models", "oversized"])
def test_invalid_runtime_telemetry_grants_no_residency(monkeypatch, raw):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(raw))
    assert budget.ollama_models("http://localhost:11434", "ps") == []


# --- resident model registry ------------------------------------------------

def _broker():
    from core.broker import ModelBroker

    return ModelBroker.get_instance()


def test_pressure_releases_idle_resident_models():
    from core.broker import ModelRole

    broker = _broker()
    calls = []
    broker.acquire(ModelRole.STT, "whisper:small", 2048, unload=lambda: calls.append("unload"))
    broker.active_models[ModelRole.STT].last_used -= 120
    try:
        released = budget.release_idle_residents(budget.ResourceSnapshot(2 * budget.GIB, None, None))
    finally:
        broker.release(ModelRole.STT)
    assert released == ["stt"]
    assert calls == ["unload"]
    assert ModelRole.STT not in broker.active_models


def test_plenty_of_memory_keeps_resident_models():
    from core.broker import ModelRole

    broker = _broker()
    calls = []
    broker.acquire(ModelRole.EMBEDDINGS, "mini-emb", 100, unload=lambda: calls.append("unload"))
    try:
        snapshot = budget.ResourceSnapshot(8 * budget.GIB, 12 * budget.GIB, 6 * budget.GIB)
        assert budget.release_idle_residents(snapshot) == []
        assert ModelRole.EMBEDDINGS in broker.active_models
        assert calls == []
    finally:
        broker.release(ModelRole.EMBEDDINGS)


def test_recent_resident_is_spared_under_moderate_pressure():
    from core.broker import ModelRole

    broker = _broker()
    broker.acquire(ModelRole.STT, "whisper:tiny", 1024, unload=lambda: None)
    try:
        snapshot = budget.ResourceSnapshot(2 * budget.GIB, None, None)
        assert budget.release_idle_residents(snapshot) == []
        assert ModelRole.STT in broker.active_models
    finally:
        broker.release(ModelRole.STT)


def test_critical_pressure_ignores_the_idle_grace_period():
    from core.broker import ModelRole

    broker = _broker()
    broker.acquire(ModelRole.STT, "whisper:tiny", 1024, unload=lambda: None)
    try:
        snapshot = budget.ResourceSnapshot(budget.GIB, None, None)
        assert budget.release_idle_residents(snapshot) == ["stt"]
    finally:
        broker.release(ModelRole.STT)


def test_failed_unload_is_contained_and_counted():
    from core.broker import ModelBroker, ModelRole

    broker = ModelBroker()

    def boom():
        raise RuntimeError("device busy")

    broker.acquire(ModelRole.TTS, "kokoro", 90, unload=boom)
    assert broker.release(ModelRole.TTS) is True
    assert broker.unload_failures == 1
    assert ModelRole.TTS not in broker.active_models


def test_acquire_evicts_an_idle_lower_priority_model(monkeypatch):
    from core.broker import ModelBroker, ModelRole

    broker = ModelBroker(budget_mb=1000)
    monkeypatch.setattr(broker, "current_vram_used_mb", lambda: 600)
    calls = []
    broker.acquire(ModelRole.EMBEDDINGS, "mini-emb", 200, unload=lambda: calls.append("emb"))
    broker.active_models[ModelRole.EMBEDDINGS].last_used -= 60
    broker.acquire(ModelRole.PLANNER, "big", 600)

    assert calls == ["emb"]
    assert ModelRole.EMBEDDINGS not in broker.active_models
    assert ModelRole.PLANNER in broker.active_models


def test_reacquiring_a_role_replaces_the_unload_callback():
    from core.broker import ModelBroker, ModelRole

    broker = ModelBroker()
    first, second = [], []
    broker.acquire(ModelRole.STT, "old", 10, unload=lambda: first.append(1))
    broker.acquire(ModelRole.STT, "new", 10, unload=lambda: second.append(1))
    broker.release(ModelRole.STT)

    assert first == []
    assert second == [1]
