import pytest

from core import llm_client, ollama_service, runtime_budget


@pytest.fixture
def routing(monkeypatch):
    monkeypatch.setattr(ollama_service, "load_runtime_config", lambda: {"preferred_model": "qwen3.5:4b"})
    monkeypatch.setattr(llm_client.OllamaClient, "is_available", lambda self: True)
    monkeypatch.setattr(llm_client.OllamaClient, "configure_thinking", lambda self: None)
    monkeypatch.setattr(llm_client.OllamaClient, "list_model_inventory", lambda self: [
        {"name": "qwen3.5:4b", "size": 3_300_000_000},
        {"name": "qwen2.5:3b-instruct", "size": 1_900_000_000}])
    monkeypatch.setattr(runtime_budget, "resource_snapshot", lambda: runtime_budget.ResourceSnapshot(3 * runtime_budget.GIB, 12 * runtime_budget.GIB, 5 * runtime_budget.GIB))
    monkeypatch.setattr(runtime_budget, "ollama_models", lambda *args: [])
    return monkeypatch


def test_primary_model_is_not_downgraded_under_pressure(routing):
    routing.setattr(runtime_budget, "model_weight_budget_bytes", lambda snapshot: 2_000_000_000)
    client, state = llm_client.create_llm_client()
    assert isinstance(client, llm_client.OfflineLLM)
    assert state == "preferred_model_deferred"
    assert "qwen3.5:4b" in client.unavailable_reason


def test_primary_recovers_when_budget_allows(routing):
    routing.setattr(runtime_budget, "model_weight_budget_bytes", lambda snapshot: 4_000_000_000)
    client, state = llm_client.create_llm_client()
    assert client.model == "qwen3.5:4b"
    assert state == "ollama:qwen3.5:4b"


def test_primary_reuses_exact_resident_when_cold_load_would_not_fit(routing):
    model = {"name": "qwen3.5:4b", "size": 3_300_000_000, "digest": "same"}
    routing.setattr(llm_client.OllamaClient, "list_model_inventory", lambda self: [model])
    routing.setattr(runtime_budget, "ollama_models", lambda *args: [
        {**model, "size_vram": model["size"], "context_length": 2048}])
    client, state = llm_client.create_llm_client()
    assert client.model == "qwen3.5:4b"
    assert state == "ollama:qwen3.5:4b"


def test_missing_primary_does_not_select_other_model(routing):
    routing.setattr(ollama_service, "load_runtime_config", lambda: {"preferred_model": "missing:4b"})
    routing.setattr(runtime_budget, "model_weight_budget_bytes", lambda snapshot: 4_000_000_000)
    client, state = llm_client.create_llm_client()
    assert isinstance(client, llm_client.OfflineLLM)
    assert state == "preferred_model_missing"


def test_runtime_outage_preserves_primary_selection(routing):
    routing.setattr(llm_client.OllamaClient, "is_available", lambda self: False)
    client, state = llm_client.create_llm_client()
    assert isinstance(client, llm_client.OfflineLLM)
    assert state == "preferred_runtime_unavailable"


def test_primary_setting_persists_when_editing_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(ollama_service, "user_data_dir", lambda: tmp_path)
    ollama_service.save_runtime_config("", "", "qwen3.5:4b")
    ollama_service.save_runtime_config("", "")
    assert ollama_service.load_runtime_config()["preferred_model"] == "qwen3.5:4b"
    with pytest.raises(ValueError):
        ollama_service.save_runtime_config("", "", "remote-cloud")
    assert ollama_service.load_runtime_config()["preferred_model"] == "qwen3.5:4b"
    ollama_service.save_runtime_config("", "", "")
    assert ollama_service.load_runtime_config()["preferred_model"] == ""


def test_settings_survive_cross_device_rename_and_partial_record(tmp_path, monkeypatch):
    import errno
    from pathlib import Path
    monkeypatch.setattr(ollama_service, "user_data_dir", lambda: tmp_path)
    ollama_service.save_runtime_config("", "", "old:3b")
    original = ollama_service.runtime_config_path().read_bytes()
    def fail_replace(*args):
        raise OSError(errno.EXDEV, "encrypted directory rename failed")
    monkeypatch.setattr(Path, "replace", fail_replace)
    for _ in range(7):
        ollama_service.save_runtime_config("", "", "qwen3.5:4b")
    assert ollama_service.load_runtime_config()["preferred_model"] == "qwen3.5:4b"
    assert ollama_service.runtime_config_path().read_bytes() == original
    assert len(list((tmp_path / "data").glob("runtime-settings-*.json"))) == 5
    (tmp_path / "data" / ("runtime-settings-" + "a" * 32 + ".json")).write_text('{"preferred_model":')
    assert ollama_service.load_runtime_config()["preferred_model"] == "qwen3.5:4b"
