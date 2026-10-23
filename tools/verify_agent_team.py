"""Live Ollama dependency diagnostic, confined to two owned temporary files."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys
import tempfile
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audit.logger import AuditLogger  # noqa: E402
from core.agent_team import AgentTeam  # noqa: E402
from core.llm_client import create_llm_client, OfflineLLM  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.runtime_budget import resource_snapshot  # noqa: E402
from tools.registry import ToolRegistry, ToolSpec, ToolResult  # noqa: E402


def main():
    ensure_local_ollama()
    llm, backend = create_llm_client()
    destination = ROOT / "build/evolution-baseline/team-live.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "backend": backend,
              "before": asdict(resource_snapshot()), "real_model_validated": False}
    if isinstance(llm, OfflineLLM):
        report.update(state="deferred", reason=llm.unavailable_reason)
    else:
        llm.keep_alive = "30s"
        with tempfile.TemporaryDirectory(prefix="nyx-team-live-") as directory:
            root = Path(directory)
            values = [secrets.randbelow(60) + 20 for _ in range(2)]
            paths = [root / "a.txt", root / "b.txt"]
            for path, value in zip(paths, values, strict=True):
                path.write_text(f"Quantidade: {value}", encoding="utf-8")
            registry = ToolRegistry()
            reads = []
            read_lock = threading.Lock()
            def read(params):
                path = Path(params.get("path", "")).resolve()
                if path not in {p.resolve() for p in paths}:
                    return ToolResult(False, error="Fora dos arquivos de diagnóstico.")
                with read_lock:
                    reads.append(path.name)
                return ToolResult(True, path.read_text(encoding="utf-8"))
            registry.register(ToolSpec("read_file", "Ler somente arquivos do diagnóstico"), read)
            tasks = [{"id": name, "role": "arquivos",
                      "task": f"Use read_file para ler {path}. Depois informe a quantidade exata; não presuma o conteúdo."}
                     for name, path in zip(("first", "second"), paths, strict=True)]
            tasks.append({"id": "sum", "role": "codigo", "depends_on": ["first", "second"],
                          "task": "Com as quantidades recebidas das duas dependências, diga os dois números e sua soma. Responda com action.type=none; não consulte ferramentas."})
            started = time.monotonic()
            result = AgentTeam(llm, registry, AuditLogger(root / "logs")).run(tasks)
            report.update(seconds=round(time.monotonic()-started, 2), ok=result.ok,
                          agents=result.meta.get("agents", []), reads=reads,
                          max_parallel=result.meta.get("max_parallel"), expected_values=values,
                          after=asdict(resource_snapshot()))
            summary = next((a.get("summary", "") for a in report["agents"] if a["id"] == "sum"), "")
            numbers = {int(n) for n in re.findall(r"\b\d+\b", summary)}
            report["real_model_validated"] = result.ok and set(reads) == {"a.txt", "b.txt"} and {*values, sum(values)} <= numbers
            report["state"] = "passed" if report["real_model_validated"] else "failed"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    archive = destination.parent / "team-attempts"
    archive.mkdir(exist_ok=True)
    (archive / f"{uuid4().hex}.json").write_text(payload, encoding="utf-8")
    destination.write_text(payload, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["real_model_validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
