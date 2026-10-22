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
