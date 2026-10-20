import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.llm_client import OLLAMA_MAX_OUTPUT_TOKENS, OllamaClient


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
