"""Live local-model multi-step diagnostic; only temporary files are readable."""

import json
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


def main():
    ensure_local_ollama()
    llm, backend = create_llm_client()
    if isinstance(llm, OfflineLLM):
        from core.runtime_budget import resource_snapshot
        from dataclasses import asdict
        destination = ROOT / "build/previews/task-live-smoke.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps({"state": "deferred", "reason": llm.unavailable_reason,
                                           "resources": asdict(resource_snapshot()), "real_model_validated": False},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError("Nenhum modelo local disponível para esse teste")
    llm.keep_alive = "0"
    with tempfile.TemporaryDirectory(prefix="nyx-task-live-") as directory:
        temporary = Path(directory)
        first, second = temporary / "a.txt", temporary / "b.txt"
        first.write_text("Quantidade A: 12", encoding="utf-8")
        second.write_text("Quantidade B: 7", encoding="utf-8")
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
                  "steps": runner.steps, "answer": result.response.speech_output,
                  "both_files_read": {s['params'].get('path') for s in runner.steps if s['ok']} == {str(first), str(second)}}
        destination = ROOT / "build/previews/task-live-smoke.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        if not report["both_files_read"] or result.needs_confirmation or not result.response.parse_ok or "19" not in result.response.speech_output:
            raise RuntimeError("O modelo não concluiu o diagnóstico; veja o relatório")


if __name__ == "__main__":
    main()
