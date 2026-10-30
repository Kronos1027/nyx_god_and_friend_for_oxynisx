"""Real local-model regression; only fixture reads may execute, no desktop input."""
# ruff: noqa: E402
from pathlib import Path
import json
import os
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cli import build_registry
from config import NyxConfig
from core.agent_loop import AgentLoop
from core.agent_team import agent_team_contract
from core.llm_client import OllamaClient
from core.task_runner import TaskRunner
from audit.logger import AuditLogger
from tools.registry import ToolSpec


def main():
    output = ROOT / "build" / "sandbox-probes" / "context-workflow-real.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="context-workflow-", dir=output.parent))
    os.chdir(work)
    paths = []
    for i in range(1, 9):
        path = work / f"numero-{i}.txt"
        path.write_text(str(i * 11), encoding="utf-8")
        paths.append(path)
    registry = build_registry(NyxConfig(allowed_roots=[work], log_dir=work / "logs"))
    registry.register(ToolSpec("agent_team", "Investigações delegadas", input_contract=agent_team_contract()), lambda p: None)
    registry.register(ToolSpec("code_task", "Propor correção de código", sensitive=True), lambda p: None)
    client = OllamaClient(model="qwen3.5:4b")
    if not client.is_available():
        raise RuntimeError("Ollama local indisponível; este diagnóstico não inicia nem substitui o serviço.")
    client.configure_thinking()
    audit = AuditLogger(work / "logs", session_id="real-context")
    loop = AgentLoop(client, registry, audit)
    runner = TaskRunner(loop)
    runner.set_budget_profile("default")
    guard = runner._guard
    def reads_only(tool, params):
        if tool == "calculator":
            guard(tool, params)
            return
        if tool != "read_file" or (work / str(params.get("path", ""))).resolve() not in paths:
            raise ValueError("Ensaio restrito às oito leituras preparadas; outra ação não foi executada.")
        guard(tool, params)
    runner._guard = reads_only
    started = time.monotonic()
    try:
        result = runner.start("Leia individualmente os oito arquivos numero-1.txt até numero-8.txt, "
                              "na pasta atual. Liste os oito valores e a soma; não invente o conteúdo.")
        rows = audit.read_all()
        reads = [step for step in runner.steps if step["tool"] == "read_file" and step["ok"] and step["verified"]]
        report = {"model": client.model, "ui_used": False, "scope": "production planner with read-only fixture and arithmetic guard",
                  "elapsed_seconds": round(time.monotonic() - started, 2), "actions": len(runner.steps),
                  "verified_reads": len(reads), "response": result.response.speech_output,
                  "values": [step["output"].strip() for step in reads],
                  "extended": any(row["event"] == "task_budget_extended" for row in rows),
                  "generations": [row["attempts"] for row in rows if row["event"] == "model_generation"],
                  "pending_confirmation": result.needs_confirmation}
        report["passed"] = (len(reads) == 8 and set(report["values"]) == {str(i * 11) for i in range(1, 9)}
                            and "396" in report["response"] and report["extended"])
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    finally:
        registry.browser_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
