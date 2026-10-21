"""Real-model write/read workflow in an isolated temporary sandbox."""
import json
import secrets
import sys
import tempfile
import time
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OfflineLLM, create_llm_client  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.task_runner import TaskRunner  # noqa: E402
from tools.file_tool import FileTool  # noqa: E402
from tools.registry import ToolRegistry, ToolResult, ToolSpec  # noqa: E402


def main():
    ensure_local_ollama()
    llm, backend = create_llm_client()
    if isinstance(llm, OfflineLLM):
        raise RuntimeError(llm.unavailable_reason)
    llm.keep_alive = "30s"
    with tempfile.TemporaryDirectory(prefix="nyx-files-live-") as directory:
        root = Path(directory)
        target = root / "note.txt"
        token = secrets.token_hex(5)
        content = f"Registro Nyx: {token}"
        file_tool = FileTool([root])
        registry = ToolRegistry()

        def write(params):
            if file_tool._resolve_sandboxed(params.get("path", "")) != target or params.get("content") != content:
                return ToolResult(False, error="O diagnóstico permite somente o arquivo e conteúdo solicitados")
            return file_tool.write_file(params)

        registry.register(ToolSpec("write_file", "Grava UTF-8: path e content", sensitive=True), write)
        registry.register(ToolSpec("read_file", "Lê UTF-8: path"), file_tool.read_file)
        loop = AgentLoop(llm, registry, AuditLogger(root / "logs", session_id="file-workflow"))
        runner = TaskRunner(loop)
        started = time.monotonic()
        result = runner.start(f"Crie {target} com exatamente este conteúdo: {content}. Depois use read_file para reler o arquivo e informe o código encontrado. Não acrescente quebra de linha ao arquivo.")
        confirmations = 0
        while result.needs_confirmation and confirmations < 3:
            pending = result.pending_action
            # Test-harness approval only: exact authorized temporary write; never a general UI bypass.
            approved = (pending.get("type") == "write_file"
                        and file_tool._resolve_sandboxed(pending["params"].get("path", "")) == target
                        and pending["params"].get("content") == content)
            confirmations += 1
            result = runner.resume(pending, approved)
        tools = [step["tool"] for step in runner.steps if step["ok"] and step["verified"]]
        checks = {"exact_file": target.is_file() and target.read_bytes() == content.encode("utf-8"),
                  "verified_write_then_read": tools == ["write_file", "read_file"],
                  "one_confirmation": confirmations == 1,
                  "requested_answer": token in result.response.speech_output,
                  "finished": not runner.active}
        passed = all(checks.values())
        report = {"backend": backend, "passed": passed, "seconds": round(time.monotonic() - started, 2),
                  "confirmation_count": confirmations, "steps": runner.steps,
                  "answer": result.response.speech_output, "expected_token": token,
                  "checks": checks, "replans": runner.replans}
        destination = ROOT / "build/previews/file-workflow.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        attempts = destination.parent / "file-attempts"
        attempts.mkdir(exist_ok=True)
        (attempts / f"{uuid4().hex}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        if not passed:
            raise RuntimeError("Fluxo de escrita e releitura reprovado; consulte o relatório")


if __name__ == "__main__":
    main()
