"""Reprodução com ferramentas reais, sem LLM: falha isolada vs. consulta de janelas."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from tools.registry import ToolRegistry, ToolSpec  # noqa: E402
from tools.ui_tool import UITool, make_ui_tool_func  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    registry = ToolRegistry()
    ui = UITool("build/diagnostic/screenshots")
    registry.register(ToolSpec("ui_action", "Diagnóstico real"), make_ui_tool_func(ui))
    loop = AgentLoop(None, registry, AuditLogger(Path("build/diagnostic"), session_id="breaker"))
    attempts = []
    # This nonexistent application never starts a process. Explicit calls exercise
    # the post-approval execution path, not a simulated model or UI approval.
    for _ in range(3):
        result = loop.confirm_pending({"type": "ui_action", "params": {
            "action": "open_app", "app": "NyxDiagnosticMissingApplication"}}, True, synthesize=False)
        attempts.append({"ok": result.tool_result.ok, "error": result.tool_result.error,
                         "verified": result.verified})
    observation = registry.execute("ui_action", {"action": "list_windows"})
    report = {"scope": "ferramenta real, sem planejador; nenhum título de janela publicado",
              "attempts": attempts, "disabled_tools": sorted(registry.disabled_tools),
              "list_windows_ok": observation.ok, "list_windows_error": observation.error,
              "elapsed_s": round(time.perf_counter() - started, 4)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
