"""Live local-model multi-step diagnostic; only temporary files are readable."""

import json
import re
import secrets
from datetime import datetime, timezone
from uuid import uuid4
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import create_llm_client, OfflineLLM  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.task_runner import TaskRunner  # noqa: E402
from tools.registry import ToolRegistry, ToolResult, ToolSpec  # noqa: E402


def evaluate_result(steps, answer, first, second, quantities):
    reads = {Path(step["params"]["path"]).resolve()
             for step in steps if step["tool"] == "read_file" and step["ok"]
             and step["verified"] is True and isinstance(step["params"].get("path"), str)}
    numbers = {int(value) for value in re.findall(r"(?<![\w-])(?<!\d[.,])\d+(?!\w|[.,]\d)", answer)}
    expected = {*quantities, sum(quantities)}
    return {"both_files_read": reads == {first.resolve(), second.resolve()},
            "expected_numbers_present": expected <= numbers}


def save_report(report):
    destination = ROOT / "build/previews/task-live-smoke.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    report["timestamp"] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    archive = destination.parent / "task-attempts"
    archive.mkdir(exist_ok=True)
    (archive / f"{uuid4().hex}.json").write_text(payload, encoding="utf-8")
    destination.write_text(payload, encoding="utf-8")


def main():
    ensure_local_ollama()
    llm, backend = create_llm_client()
    if isinstance(llm, OfflineLLM):
        from core.runtime_budget import resource_snapshot
        from dataclasses import asdict
        save_report({"state": "deferred", "reason": llm.unavailable_reason,
                     "resources": asdict(resource_snapshot()), "real_model_validated": False})
        raise RuntimeError("Nenhum modelo local disponível para esse teste")
    llm.keep_alive = "30s"
    with tempfile.TemporaryDirectory(prefix="nyx-task-live-") as directory:
        temporary = Path(directory)
        first, second = temporary / "a.txt", temporary / "b.txt"
        quantities = (secrets.randbelow(80) + 10, secrets.randbelow(80) + 10)
        first.write_text(f"Quantidade A: {quantities[0]}", encoding="utf-8")
        second.write_text(f"Quantidade B: {quantities[1]}", encoding="utf-8")
        registry = ToolRegistry()

        def read(params):
            path = Path(params.get("path", "")).resolve()
            if path not in {first.resolve(), second.resolve()}:
                return ToolResult(False, error="Somente os dois arquivos temporários são permitidos no diagnóstico")
            return ToolResult(True, output=path.read_text(encoding="utf-8"))

        registry.register(ToolSpec("read_file", "Ler os arquivos temporários do teste"), read)
        loop = AgentLoop(llm, registry, AuditLogger(temporary / "logs", session_id="live-task"))
        runner = TaskRunner(loop)
        started = time.monotonic()
        result = runner.start(f"Leia primeiro o arquivo {first} usando read_file. Depois leia {second} usando read_file. Só depois de ler os dois, diga as quantidades e a soma. Não presuma o conteúdo dos arquivos.")
        report = {"backend": backend, "seconds": round(time.monotonic() - started, 2),
                  "schema_valid": result.response.parse_ok, "needs_confirmation": result.needs_confirmation,
                  "pending_action": result.pending_action, "steps": runner.steps, "answer": result.response.speech_output,
                  "expected_quantities": quantities}
        report.update(evaluate_result(runner.steps, result.response.speech_output, first, second, quantities))
        report["real_model_validated"] = bool(report["both_files_read"] and report["expected_numbers_present"]
                                              and not result.needs_confirmation and result.response.parse_ok)
        report["state"] = "passed" if report["real_model_validated"] else "failed"
        save_report(report)
        print(json.dumps(report, ensure_ascii=False))
        if not report["real_model_validated"]:
            raise RuntimeError("O modelo não concluiu o diagnóstico; veja o relatório")


if __name__ == "__main__":
    main()
