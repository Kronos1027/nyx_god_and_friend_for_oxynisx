"""Real local-model skill discovery and permission-gated temporary file workflow."""

import json
from pathlib import Path
import secrets
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OfflineLLM, create_llm_client  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.skills import SkillManager  # noqa: E402
from core.task_runner import TaskRunner  # noqa: E402
from tools.file_tool import FileTool  # noqa: E402
from tools.registry import ToolRegistry, ToolResult, ToolSpec  # noqa: E402
from tools.skill_tool import register_skill_tool  # noqa: E402


def main():
    ensure_local_ollama()
    llm, backend = create_llm_client()
    if isinstance(llm, OfflineLLM) or getattr(llm, "model", "").casefold() != "qwen3.5:4b":
        raise RuntimeError(f"Ensaio exige o modelo escolhido Qwen3.5:4b; backend disponível: {backend}")
    with tempfile.TemporaryDirectory(prefix="nyx-skill-live-") as directory:
        root = Path(directory)
        target = root / "work" / "nota.txt"
        expected = "Código da fixture: " + secrets.token_hex(5)
        registry = ToolRegistry()
        files = FileTool([target.parent])
        register_skill_tool(registry, root / "skills")
        SkillManager(root / "skills").promote_task_to_skill(
            "nota-demo", "Salva e verifica uma nota de ensaio", [
                {"type": "write_file", "params": {"path": str(target), "content": expected}},
                {"type": "read_file", "params": {"path": str(target)}},
            ])

        def write(params):
            if files._resolve_sandboxed(params.get("path", "")) != target or params.get("content") != expected:
                return ToolResult(False, error="O ensaio autoriza somente o arquivo e conteúdo da fixture.")
            return files.write_file(params)

        def read(params):
            if files._resolve_sandboxed(params.get("path", "")) != target:
                return ToolResult(False, error="O ensaio permite ler somente a nota temporária.")
            return files.read_file(params)

        registry.register(ToolSpec("write_file", "Grava nota UTF-8: path e content", sensitive=True), write)
        registry.register(ToolSpec("read_file", "Lê nota UTF-8: path"), read)
        runner = TaskRunner(AgentLoop(llm, registry, AuditLogger(root / "logs", session_id="skill-live")))
        started = time.monotonic()
        result = runner.start(
            "Pesquise no catálogo skills o procedimento de nota de ensaio. Carregue seu conteúdo com get, "
            "siga as etapas pelas ferramentas normais e respeite as confirmações. "
            "Após reler o arquivo criado, informe o código encontrado. Não presuma o conteúdo do procedimento.")
        confirmations = 0
        before_approval_absent = True
        while result.needs_confirmation and confirmations < 2:
            pending = result.pending_action
            before_approval_absent &= not target.exists()
            approved = (pending.get("type") == "write_file"
                        and files._resolve_sandboxed(pending["params"].get("path", "")) == target
                        and pending["params"].get("content") == expected)
            confirmations += 1
            result = runner.resume(pending, approved)
        actions = [(step["tool"], step["params"].get("op")) for step in runner.steps if step["ok"]]
        checks = {"discovered": ("skills", "search") in actions or ("skills", "list") in actions,
                  "loaded": ("skills", "get") in actions,
                  "exact_file": target.exists() and target.read_bytes() == expected.encode(),
                  "read_back": ("read_file", None) in actions,
                  "permission_gate": confirmations == 1 and before_approval_absent,
                  "answer": expected.split()[-1] in result.response.speech_output,
                  "finished": not runner.active}
        report = {"backend": backend, "model": llm.model, "passed": all(checks.values()),
                  "checks": checks, "seconds": round(time.monotonic() - started, 2),
                  "steps": runner.steps, "answer": result.response.speech_output}
        destination = ROOT / "build/evolution-baseline/skill-attempts"
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"{uuid4().hex}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(path), **{key: report[key] for key in ("passed", "checks", "seconds", "answer")}}, ensure_ascii=False))
        if not report["passed"]:
            raise RuntimeError("Fluxo de skill não completou todos os critérios; tentativa preservada.")


if __name__ == "__main__":
    main()
