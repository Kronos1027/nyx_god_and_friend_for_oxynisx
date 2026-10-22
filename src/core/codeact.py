"""Task planning and repair helpers. Generated-code execution requires real isolation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tools.registry import ToolResult

log = logging.getLogger(__name__)


@dataclass
class CodeActStep:
    step_num: int
    code: str
    language: str
    exit_code: int
    stdout: str
    stderr: str
    ok: bool
    diagnosis: Optional[str] = None
    applied_fix: Optional[str] = None


@dataclass
class TaskPlan:
    task_id: str
    title: str
    workspace_dir: Path
    todo_file: Path
    items: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def save(self) -> None:
        """Persiste o plano vivo todo.md no disco."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"# Tarefa: {self.title}", f"ID: {self.task_id}", "", "## Passos Planejados:"]
        for idx, item in enumerate(self.items, start=1):
            status = item.get("status", "pending")
            icon = "[x]" if status == "completed" else "[-]" if status == "failed" else "[ ]"
            lines.append(f"{idx}. {icon} {item.get('title', 'Sem título')}")
            if notes := item.get("notes"):
                lines.append(f"   - Nota: {notes}")
        self.todo_file.write_text("\n".join(lines), encoding="utf-8")

    def update_item_status(self, index: int, status: str, notes: Optional[str] = None) -> None:
        if 0 <= index < len(self.items):
            self.items[index]["status"] = status
            if notes:
                self.items[index]["notes"] = notes
            self.save()


class CodeActEngine:
    """Motor de execução, depuração reflexiva e entrega de código."""

    def __init__(
        self,
        base_workspace: Path = Path("workspace"),
        timeout_seconds: int = 25,
        max_repair_attempts: int = 3,
        llm_repair_callback: Optional[Callable[[str, str, str], str]] = None,
    ) -> None:
        self.base_workspace = Path(base_workspace).resolve()
        self.timeout_seconds = timeout_seconds
        self.max_repair_attempts = max_repair_attempts
        self.llm_repair_callback = llm_repair_callback
        self.base_workspace.mkdir(parents=True, exist_ok=True)

    def init_task(self, task_name: str, steps: List[str]) -> TaskPlan:
        """Inicializa um novo ambiente de tarefa isolado com todo.md."""
        clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in task_name).strip("_")
        clean_name = clean_name or "tarefa_nyx"
        task_dir = (self.base_workspace / clean_name).resolve()
        if task_dir == self.base_workspace or self.base_workspace not in task_dir.parents:
            raise ValueError("Pasta da tarefa fora do workspace")
        task_dir.mkdir(parents=True, exist_ok=True)

        todo_file = task_dir / "todo.md"
        items = [{"title": s, "status": "pending"} for s in steps]
        plan = TaskPlan(
            task_id=clean_name,
            title=task_name,
            workspace_dir=task_dir,
            todo_file=todo_file,
            items=items,
        )
        plan.save()
        return plan

    def run_in_sandbox(
        self,
        code: str,
        task_dir: Path,
        language: str = "python",
        filename: Optional[str] = None,
    ) -> tuple[int, str, str]:
        """Fail closed until a real isolated execution backend is configured."""
        return 126, "", (
            "Execução bloqueada: sandbox real indisponível. "
            "Um subprocesso com CWD separado não isola arquivos, rede ou credenciais."
        )

    def execute_and_heal(
        self,
        task_name: str,
        code: str,
        language: str = "python",
        filename: Optional[str] = None,
    ) -> ToolResult:
        """Executa o código e, se falhar, tenta auto-diagnosticar e corrigir em loop reflexivo."""
        task_dir = (self.base_workspace / task_name).resolve()
        if task_dir == self.base_workspace or self.base_workspace not in task_dir.parents:
            return ToolResult(False, error="Pasta da tarefa fora do workspace")
        if filename:
            target = (task_dir / filename).resolve()
            if Path(filename).is_absolute() or ":" in filename or task_dir not in target.parents:
                return ToolResult(False, error="Arquivo fora da pasta da tarefa")

        current_code = code
        history: List[CodeActStep] = []

        for attempt in range(1, self.max_repair_attempts + 1):
            exit_code, stdout, stderr = self.run_in_sandbox(
                code=current_code,
                task_dir=task_dir,
                language=language,
                filename=filename,
            )

            if exit_code == 126:
                return ToolResult(False, error=stderr, meta={"blocked": True, "reason": "isolation_unavailable", "attempts": attempt})
            is_ok = (exit_code == 0)
            step = CodeActStep(
                step_num=attempt,
                code=current_code,
                language=language,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                ok=is_ok,
            )
            history.append(step)

            if is_ok:
                return ToolResult(
                    ok=True,
                    output=stdout or "(Executado com sucesso sem saída de terminal)",
                    meta={
                        "task_dir": str(task_dir),
                        "attempts": attempt,
                        "history": [s.__dict__ for s in history],
                    },
                )

            # Falha detectada: diagnostica
            diagnosis = self._diagnose_error(stderr, stdout, language)
            step.diagnosis = diagnosis
            log.warning(f"[CodeAct] Tentativa {attempt}/{self.max_repair_attempts} falhou: {diagnosis}")

            if attempt < self.max_repair_attempts:
                # Tenta corrigir deterministicamente ou via callback
                fixed_code = self._attempt_repair(current_code, stderr, diagnosis)
                if fixed_code and fixed_code != current_code:
                    step.applied_fix = "Reparo determinístico aplicado"
                    current_code = fixed_code
                elif self.llm_repair_callback:
                    try:
                        llm_fix = self.llm_repair_callback(current_code, stderr, diagnosis)
                        if llm_fix and llm_fix != current_code:
                            step.applied_fix = "Reparo via LLM aplicado"
                            current_code = llm_fix
                    except Exception as err:
                        log.error(f"[CodeAct] Falha no callback de reparo do LLM: {err}")

        # Se todas as tentativas esgotaram
        return ToolResult(
            ok=False,
            output=stdout,
            error=(
                f"CodeAct falhou após {self.max_repair_attempts} tentativas.\n"
                f"Último erro: {stderr.strip()}\n"
                f"Diagnóstico: {history[-1].diagnosis}"
            ),
            meta={
                "task_dir": str(task_dir),
                "attempts": self.max_repair_attempts,
                "history": [s.__dict__ for s in history],
            },
        )

    def _diagnose_error(self, stderr: str, stdout: str, language: str) -> str:
        """Diagnóstico determinístico dos erros mais comuns de script."""
        combined = (stderr + "\n" + stdout).lower()
        if "modulenotfounderror" in combined or "no module named" in combined:
            return "Modulo/biblioteca ausente no ambiente Python."
        if "syntaxerror" in combined:
            return "Erro de sintaxe no codigo gerado."
        if "filenotfounderror" in combined:
            return "Arquivo ou caminho referenciado nao encontrado."
        if "permissionerror" in combined:
            return "Acesso negado ou falta de permissao ao recurso."
        if "timeout" in combined:
            return "Operacao excedeu o limite de tempo estipulado."
        if "indentationerror" in combined:
            return "Erro de identacao no script Python."
        if "nameerror" in combined:
            return "Variavel ou funcao utilizada sem definicao previa."
        return "Erro de execucao generico durante o runtime do script."

    def _attempt_repair(self, code: str, stderr: str, diagnosis: str) -> Optional[str]:
        """Aplica regras determinísticas de correção para erros conhecidos simples."""
        if "ModuleNotFoundError: No module named 'json'" in stderr or "name 'json' is not defined" in stderr:
            return "import json\n" + code
        if "ModuleNotFoundError: No module named 'sys'" in stderr or "name 'sys' is not defined" in stderr:
            return "import sys\n" + code
        if "ModuleNotFoundError: No module named 'os'" in stderr or "name 'os' is not defined" in stderr:
            return "import os\n" + code
        if "ModuleNotFoundError: No module named 'pathlib'" in stderr or "name 'Path' is not defined" in stderr:
            return "from pathlib import Path\n" + code
        return None
