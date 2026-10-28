"""Real local model probe with synthetic prompts; no proposed tool is executed."""

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.llm_client import OllamaClient, parse_response  # noqa: E402
from core.ollama_service import load_runtime_config  # noqa: E402
from core import runtime_budget  # noqa: E402


def main():
    model = load_runtime_config().get("preferred_model")
    if not model:
        raise RuntimeError("Selecione um modelo local antes do ensaio.")
    client = OllamaClient(model=model, timeout=90)
    client.configure_thinking()
    actual = runtime_budget.post_ollama_json
    report = {"model": model, "think": client.think, "tool_executions": 0, "cases": []}
    scenarios = [
        ("greeting", "Bom dia, Nyx!", [], False),
        ("media_status", "O Spotify está aberto no navegador. Consulte o estado de reprodução com media_status antes de decidir a próxima etapa.",
         [{"name": "browser", "description": "Consulta de reprodução: params.action=media_status."}], False),
        ("injected_truncation", "Bom dia, Nyx!", [], True),
    ]
    try:
        for name, prompt, tools, inject in scenarios:
            responses = []
            def post(url, payload, timeout, responses=responses, inject=inject):
                data = actual(url, payload, timeout)
                message = data.get("message", {})
                responses.append({"done_reason": data.get("done_reason"), "eval_count": data.get("eval_count"),
                                  "content_characters": len(message.get("content", "")),
                                  "thinking_characters": len(message.get("thinking", ""))})
                if inject and len(responses) == 1:
                    data = dict(data, done_reason="length", message=dict(message, content=message.get("content", "")[:40]))
                return data
            runtime_budget.post_ollama_json = post
            started = time.monotonic()
            case = {"name": name, "fault_injected": inject, "responses": responses}
            try:
                result = parse_response(client.generate(prompt, task_tools=tools))
                case.update(parse_ok=result.parse_ok, action=result.action.type,
                            operation=result.action.params.get("action"),
                            valid_intent=(result.action.type == ("browser" if name == "media_status" else "none")
                                          and (name != "media_status" or result.action.params.get("action") == "media_status")))
            except Exception as exc:
                case.update(parse_ok=False, error=str(exc))
            case.update(seconds=round(time.monotonic() - started, 2), attempts=client.generation_report)
            report["cases"].append(case)
            print(json.dumps(case, ensure_ascii=True), flush=True)
    finally:
        runtime_budget.post_ollama_json = actual
        destination = ROOT / "build/sandbox-probes/json-recovery-live.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if all(case.get("parse_ok") and case.get("valid_intent") for case in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
