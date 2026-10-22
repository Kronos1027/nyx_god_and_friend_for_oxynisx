"""Bounded code loop: run the project's tests, ask the model for a fix, retry.

The loop only touches text files inside the repository the user pointed at, and
it proposes changes instead of writing them unless ``apply`` is explicitly set.
Every file it overwrites is backed up first and restored if the tests still fail
after the last round.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MAX_ROUNDS = 3
MAX_EDITS = 5
MAX_FILE_BYTES = 200_000
TEST_TIMEOUT_SECONDS = 300
ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".cfg", ".ini", ".yaml", ".yml"}
OUTPUT_TAIL_CHARS = 6000
CODE_TASK_SCHEMA = {
    "type": "object",
    "required": ["reasoning", "edits", "summary"],
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "content"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


class CodeTaskError(RuntimeError):
    """The request is unsafe or malformed."""


@dataclass(frozen=True)
class CodeEdit:
    path: Path
    relative: str
    content: str


def _tail(text: str, limit: int = OUTPUT_TAIL_CHARS) -> str:
    text = text or ""
    return text[-limit:]


def _extract_json(raw: str) -> dict:
    """Accept a fenced block or bare JSON; reject anything else."""
    candidate = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.S)
    if fenced:
        candidate = fenced.group(1)
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start:end + 1]
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError) as exc:
        raise CodeTaskError("O modelo não devolveu um plano JSON válido.") from exc
    if not isinstance(data, dict):
        raise CodeTaskError("O plano precisa ser um objeto JSON.")
    return data


class CodeTaskRunner:
    """Run tests and let the model patch the repository, within hard limits."""

    def __init__(self, llm, allowed_roots: list[Path], runner=None) -> None:
        self.llm = llm
        self.roots = [Path(root).resolve() for root in allowed_roots]
        self._runner = runner or self._run_tests

    # -- public ------------------------------------------------------------
    def run(self, params: dict) -> dict:
        from tools.registry import ToolResult

        try:
            repo = self._resolve_repo(params.get("path"))
            task = self._clean_task(params.get("task"))
            apply_changes = params.get("apply", False)
            if type(apply_changes) is not bool:
                raise CodeTaskError("apply precisa ser um booleano explícito.")
            max_rounds = int(params.get("max_rounds") or 2)
        except (CodeTaskError, ValueError, TypeError) as exc:
            return ToolResult(False, error=str(exc), meta={"action": "code_task"})
        max_rounds = max(1, min(MAX_ROUNDS, max_rounds))

        backups: dict[Path, bytes | None] = {}
        last_output = ""
        rounds = 0
        try:
            if params.get("operation") == "propose":
                if apply_changes:
                    raise CodeTaskError("Uma proposta não pode aplicar alterações.")
                output = params.get("test_output")
                if not isinstance(output, str) or not output.strip() or len(output) > 12000:
                    raise CodeTaskError("Forneça test_output com 1 a 12000 caracteres; ele não será executado.")
                edits = self._propose(repo, task, output, 1)
                return ToolResult(True, "Proposta criada a partir do relatório fornecido; testes não executados.",
                                  meta={"action": "code_task", "applied": False, "tests_executed": False,
                                        "proposed": [{"path": e.relative, "content": e.content} for e in edits]})
            python = self._resolve_python(repo, params.get("python"))
            code, output = self._runner(repo, python)
            last_output = output
            rounds = 1
            if code == 0:
                return ToolResult(
                    True,
                    f"Testes passaram na rodada {rounds}.\n\n{_tail(output)}",
                    meta={"action": "code_task", "rounds": rounds, "repo": str(repo),
                          "applied": False, "passed": True},
                )
            for attempt in range(1, max_rounds + 1):
                edits = self._propose(repo, task, output, attempt)
                if not apply_changes:
                    summary = "\n".join(
                        f"- {edit.relative}: {len(edit.content.splitlines())} linhas propostas" for edit in edits
                    )
                    return ToolResult(
                        True,
                        f"Testes falharam. Proposta de correção (nada foi gravado):\n{summary}\n\n"
                        f"Trecho da falha:\n{_tail(output, 1500)}",
                        meta={"action": "code_task", "proposed": [
                            {"path": edit.relative, "content": edit.content} for edit in edits
                        ], "rounds": rounds, "applied": False},
                    )
                for edit in edits:
                    backups.setdefault(edit.path, edit.path.read_bytes() if edit.path.exists() else None)
                    edit.path.parent.mkdir(parents=True, exist_ok=True)
                    edit.path.write_text(edit.content, encoding="utf-8")
                    log.info("code_task: escreveu %s", edit.relative)
                code, output = self._runner(repo, python)
                last_output = output
                rounds += 1
                if code == 0:
                    return ToolResult(
                        True,
                        f"Testes passaram na rodada {rounds}.\n\n{_tail(output)}",
                        meta={"action": "code_task", "rounds": rounds, "repo": str(repo),
                              "applied": True, "passed": True},
                    )
        except Exception as exc:
            restored = self._restore(backups)
            detail = str(exc) if isinstance(exc, CodeTaskError) else f"{type(exc).__name__}: {exc}"
            return ToolResult(False, error=detail,
                              meta={"action": "code_task", "rounds": rounds, "applied": bool(backups),
                                    "reverted": restored if backups else None})

        restored = self._restore(backups)
        detail = "Todas as edições foram revertidas." if restored else "Reversão parcial."
        return ToolResult(
            False,
            error=f"Os testes continuaram falhando após {max_rounds} tentativa(s). {detail}",
            output=_tail(last_output),
            meta={"action": "code_task", "rounds": rounds, "applied": True, "reverted": restored},
        )

    # -- internals ---------------------------------------------------------
    def _resolve_repo(self, raw: object) -> Path:
        if not raw:
            raise CodeTaskError("Informe a pasta do projeto.")
        repo = Path(str(raw)).expanduser().resolve()
        if not repo.is_dir():
            raise CodeTaskError("A pasta do projeto não existe.")
        if not any(repo == root or root in repo.parents for root in self.roots):
            raise CodeTaskError("A pasta do projeto está fora das raízes permitidas.")
        return repo

    @staticmethod
    def _clean_task(raw: object) -> str:
        task = str(raw or "").strip()
        if not task:
            raise CodeTaskError("Descreva o que deve ser corrigido.")
        if len(task) > 800:
            raise CodeTaskError("A descrição da tarefa é longa demais.")
        return task

    @staticmethod
    def python_executable() -> str:
        """Inside the frozen app sys.executable is Nyx.exe, not an interpreter."""
        if not getattr(sys, "frozen", False):
            return sys.executable
        for name in ("python", "python3", "py"):
            found = shutil.which(name)
            if found:
                return found
        return "python"

    def _resolve_python(self, repo: Path, requested: object = None) -> str:
        """Prefer the project's own virtualenv; a repo usually pins its deps."""
        if requested:
            candidate = Path(str(requested)).expanduser()
            if not candidate.is_file():
                raise CodeTaskError("O interpretador Python indicado não existe.")
            return str(candidate)
        env_python = os.environ.get("NYX_PYTHON", "")
        if env_python and Path(env_python).is_file():
            return env_python
        for relative in (".venv/Scripts/python.exe", ".venv/bin/python",
                         "venv/Scripts/python.exe", "venv/bin/python"):
            candidate = repo / relative
            if candidate.is_file():
                return str(candidate)
        return self.python_executable()

    def _run_tests(self, repo: Path, python: str | None = None) -> tuple[int, str]:
        # Repository tests (including conftest.py/plugins) are arbitrary code.
        # A working directory and approval alone do not provide isolation.
        raise CodeTaskError(
            "Execução de testes bloqueada: nenhum executor com isolamento real está configurado. "
            "Use operation='propose' e test_output para obter uma proposta sem executar código."
        )




    def _propose(self, repo: Path, task: str, output: str, round_index: int) -> list[CodeEdit]:
        prompt = (
            "Você é a Nyx corrigindo um repositório local com testes falhando.\n"
            f"Rodada {round_index}. Objetivo do usuário: {task}\n\n"
            "Saída da suíte (final):\n"
            f"{_tail(output, 4000)}\n\n"
            "Responda SOMENTE com JSON no formato:\n"
            '{"reasoning": "...", "edits": [{"path": "relativo/ao/repo.py", "content": "arquivo completo"}], '
            '"summary": "..."}\n'
            f"Regras: no máximo {MAX_EDITS} arquivos; caminhos relativos dentro do repositório; "
            "conteúdo completo do arquivo; sem binários; mudanças mínimas para os testes passarem."
        )
        try:
            import inspect

            kwargs = {}
            if hasattr(self.llm, "generate"):
                params = inspect.signature(self.llm.generate).parameters
                if "schema" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                    kwargs["schema"] = CODE_TASK_SCHEMA
                if "max_output_tokens" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                    kwargs["max_output_tokens"] = 1024
            raw = self.llm.generate(prompt, history=[], **kwargs)
        except Exception as exc:
            raise CodeTaskError(f"Modelo indisponível: {type(exc).__name__}: {exc}") from exc

        plan = _extract_json(raw)
        raw_edits = plan.get("edits")
        if not isinstance(raw_edits, list) or not raw_edits:
            raise CodeTaskError("O modelo não propôs nenhuma edição.")
        if len(raw_edits) > MAX_EDITS:
            raise CodeTaskError(f"O modelo propôs mais de {MAX_EDITS} arquivos.")

        edits: list[CodeEdit] = []
        for item in raw_edits:
            if not isinstance(item, dict):
                raise CodeTaskError("Edição inválida no plano.")
            relative = str(item.get("path") or "").strip().replace("\\", "/")
            content = item.get("content")
            if not relative or not isinstance(content, str):
                raise CodeTaskError("Cada edição precisa de path e content.")
            if Path(relative).is_absolute() or ":" in relative or any(
                part.lower() in {".git", ".venv", "venv", ".env"} for part in Path(relative).parts
            ):
                raise CodeTaskError(f"Caminho protegido ou absoluto: {relative}")
            target = (repo / relative).resolve()
            if target != repo and repo not in target.parents:
                raise CodeTaskError(f"Caminho fora do repositório: {relative}")
            if target.suffix.lower() not in ALLOWED_SUFFIXES:
                raise CodeTaskError(f"Tipo de arquivo não permitido: {relative}")
            if len(content.encode("utf-8")) > MAX_FILE_BYTES:
                raise CodeTaskError(f"Arquivo proposto grande demais: {relative}")
            edits.append(CodeEdit(target, relative, content))
        return edits

    @staticmethod
    def _restore(backups: dict[Path, bytes | None]) -> bool:
        ok = True
        for path, original in backups.items():
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            except OSError:
                ok = False
                log.warning("code_task: falha ao restaurar %s", path, exc_info=True)
        return ok


def make_code_task_tool_func(llm, allowed_roots: list[Path]):
    runner = CodeTaskRunner(llm, allowed_roots)

    def run(params: dict):
        return runner.run(params)

    return run
