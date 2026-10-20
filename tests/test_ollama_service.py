import json

import pytest

from core import ollama_service


def test_existing_server_is_reused_without_spawning_or_restarting(monkeypatch):
    monkeypatch.setattr(ollama_service, "_owned_process", None)
    monkeypatch.setattr(ollama_service, "_healthy", lambda host: True)
    monkeypatch.setattr(ollama_service.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Existing service must not be restarted"))
    result = ollama_service.ensure_local_ollama()
    assert result.ready and not result.started_by_nyx


def test_new_local_server_uses_configured_store_and_resource_limits(tmp_path, monkeypatch):
    binary = tmp_path / "ollama.exe"
    binary.touch()
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("NYX_OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.setattr(ollama_service, "user_data_dir", lambda: tmp_path)
    monkeypatch.setattr(ollama_service, "_owned_process", None)
    monkeypatch.setattr(ollama_service, "load_runtime_config", lambda: {"ollama_executable": str(binary), "models_directory": str(models)})
    probes = iter([False, True])
    monkeypatch.setattr(ollama_service, "_healthy", lambda host: next(probes))
    monkeypatch.setattr(ollama_service.socket, "create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionRefusedError()))
    calls = []

    class Process:
        pid = 1234

        def poll(self):
            return None

    def spawn(args, **kwargs):
        calls.append((args, kwargs))
        return Process()

    monkeypatch.setattr(ollama_service.subprocess, "Popen", spawn)
    result = ollama_service.ensure_local_ollama()
    assert result.ready and result.started_by_nyx
    assert calls[0][0] == [str(binary), "serve"]
    environment = calls[0][1]["env"]
    assert environment["OLLAMA_MODELS"] == str(models)
    assert environment["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert environment["OLLAMA_NUM_PARALLEL"] == "1"
    assert environment["OLLAMA_MAX_LOADED_MODELS"] == "1"
    assert environment["OLLAMA_MAX_QUEUE"] == "8"
    assert environment["OLLAMA_NO_CLOUD"] == "1"


def test_remote_endpoint_never_starts_a_local_service(monkeypatch):
    monkeypatch.setenv("NYX_OLLAMA_HOST", "https://example.invalid")
    monkeypatch.setattr(ollama_service, "_healthy", lambda host: False)
    monkeypatch.setattr(ollama_service.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Remote endpoint must not spawn a local server"))
    assert not ollama_service.ensure_local_ollama().ready


def test_runtime_paths_are_validated_before_persisting(tmp_path, monkeypatch):
    monkeypatch.setattr(ollama_service, "user_data_dir", lambda: tmp_path)
    binary = tmp_path / "ollama.exe"
    binary.touch()
    models = tmp_path / "models"
    models.mkdir()
    ollama_service.save_runtime_config(str(binary), str(models))
    previous = ollama_service.runtime_config_path().read_text(encoding="utf-8")
    assert json.loads(previous)["models_directory"] == str(models.resolve())
    with pytest.raises(ValueError):
        ollama_service.save_runtime_config(str(tmp_path / "missing.exe"), str(models))
    assert ollama_service.runtime_config_path().read_text(encoding="utf-8") == previous
