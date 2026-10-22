import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.llm_client import OLLAMA_MAX_OUTPUT_TOKENS, OllamaClient


def test_task_tools_narrow_schema_without_mutating_shared_schema(monkeypatch):
    from core.llm_client import NYX_JSON_SCHEMA
    captured = []
    def post(url, payload, timeout):
        captured.append(payload)
        return {"message": {"content": "{}"}}
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", post)
    client = OllamaClient()
    client.generate("Leia", task_tools=[{"name": "read_file", "description": "Read"}])
    payload = captured[-1]
    assert payload["format"]["properties"]["action"]["properties"]["type"]["enum"] == ["none", "read_file"]
    assert len(payload["messages"][0]["content"]) < 1000
    assert "shell" in NYX_JSON_SCHEMA["properties"]["action"]["properties"]["type"]["enum"]
    client.generate("Converse")
    assert captured[-1]["format"] is NYX_JSON_SCHEMA


def test_empty_task_registry_only_allows_conversation(monkeypatch):
    captured = []
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", lambda url, payload, timeout: captured.append(payload) or {})
    OllamaClient().generate("Oi", task_tools=[])
    assert captured[0]["format"]["properties"]["action"]["properties"]["type"]["enum"] == ["none"]


def test_fast_thinking_mode_requires_runtime_metadata(monkeypatch):
    import io
    import urllib.request
    metadata = {"thinking": {"values": [False, True], "default": True}}
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(metadata).encode()))
    client = OllamaClient(model="qwen3.5:4b")
    client.configure_thinking()
    assert client.think is False
    captured = []
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", lambda url, payload, timeout: captured.append(payload) or {})
    client.generate("Oi")
    assert captured[-1]["think"] is False
    metadata["thinking"]["values"] = ["low", "high"]
    client.configure_thinking()
    client.generate("Oi")
    assert "think" not in captured[-1]


def test_ollama_generation_has_hard_output_token_limit(monkeypatch):
    import urllib.request

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"message": {"content": "{}"}}).encode()

    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    from core import runtime_budget

    monkeypatch.setattr(runtime_budget, "ollama_models", lambda host, endpoint: [
        {"name": "qwen2.5:3b-instruct", "size": 1}
    ] if endpoint == "tags" else [])

    monkeypatch.setattr(
        runtime_budget,
        "resource_snapshot",
        lambda: runtime_budget.ResourceSnapshot(
            ram_available_bytes=16 * runtime_budget.GIB,
            vram_total_bytes=12 * runtime_budget.GIB,
            vram_free_bytes=10 * runtime_budget.GIB,
        ),
    )
    OllamaClient().generate("responda curto")
    assert captured["payload"]["options"]["num_predict"] == OLLAMA_MAX_OUTPUT_TOKENS
    assert captured["payload"]["options"]["num_ctx"] == 4096
