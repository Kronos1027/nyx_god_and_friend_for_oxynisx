"""Nyx — audit/logger.py

Log JSONL append-only de TODA decisão+ação+resultado (seção 4.4 do prompt
mestre). Obrigatório desde a fase 1. Cada linha é um evento JSON com
timestamp UTC.

Formato das linhas:
{"ts": "...", "session": "...", "event": "...", ...payload}
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    """Append-only JSONL logger, thread-safe."""

    def __init__(self, log_dir: Path, session_id: str = "default") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.path = self.log_dir / f"nyx_audit_{session_id}.jsonl"
        self._lock = threading.Lock()

    def log_event(self, event: str, **payload: object) -> dict:
        """Grava um evento append-only. Nunca quebra o fluxo do agente."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "session": self.session_id,
            "event": event,
            **payload,
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return entry

    def log_decision(
        self,
        user_input: str,
        response_raw: str,
        parse_ok: bool,
        parse_error: str | None,
        action_type: str,
        action_params: dict,
        requires_confirmation: bool,
        executed: bool,
        result_ok: bool | None,
        result_output: str | None,
        mode: str,
    ) -> dict:
        """Ciclo completo de decisão (seção 4.4): input -> LLM -> ação -> resultado."""
        return self.log_event(
            "decision",
            user_input=user_input,
            llm_raw=response_raw,
            parse_ok=parse_ok,
            parse_error=parse_error,
            action_type=action_type,
            action_params=action_params,
            requires_confirmation=requires_confirmation,
            executed=executed,
            result_ok=result_ok,
            result_output=(result_output or "")[:2000],  # trunca outputs gigantes
            mode=mode,
        )

    def log_security(self, code: str, detail: str, **extra: object) -> dict:
        """Eventos de segurança: tentativa de ativação ilegal, bloqueios etc."""
        return self.log_event("security", code=code, detail=detail, **extra)

    def read_all(self) -> list[dict]:
        """Lê todas as entradas (para verificação/testes)."""
        if not self.path.exists():
            return []
        out: list[dict] = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
