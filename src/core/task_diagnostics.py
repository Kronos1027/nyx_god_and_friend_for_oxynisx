"""Read-only, privacy-safe snapshot of Nyx's persisted task progress.

Unlike TaskJournal this reader does not acquire its exclusive runtime lease,
allowing diagnostics while Nyx is running. Only whitelist-derived metrics
are exposed; prompts, paths, file contents and LLM outputs are omitted.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3

from core.task_health import task_health
from core.task_journal import TaskJournal


def read_task_diagnostics(db_path: Path, *, limit: int = 20) -> dict:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("O limite deve estar entre 1 e 100.")
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError("Histórico local não encontrado.")
    # Query-only SQLite connection does not block the agent's OS lease and
    # makes no mutation to persistent data or on-disk WAL metadata.
    uri = db_path.resolve().as_uri() + "?mode=ro"
    reports = []
    invalid = 0
    with sqlite3.connect(uri, uri=True, timeout=2) as conn:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute("SELECT payload FROM tasks ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        for (payload,) in rows:
            if not isinstance(payload, str) or len(payload.encode("utf-8")) > TaskJournal.MAX_PAYLOAD:
                invalid += 1
                continue
            try:
                item = json.loads(payload)
                status = task_health(item)
            except (TypeError, ValueError, KeyError):
                invalid += 1
                continue
            reports.append(status)
    statuses = Counter(x["status"] for x in reports)
    return {
        "inspected": len(reports),
        "invalid_records": invalid,
        "states": dict(sorted(statuses.items())),
        "needs_manual_review": sum(x["requires_manual_review"] for x in reports),
        "verified_goals": sum(x["goal_verified"] for x in reports),
        "total_verified_actions": sum(x["steps_verified"] for x in reports),
        "tasks": reports,
        "notes": "Somente métricas locais. Nenhum texto de pedido, arquivo ou resposta do modelo é exportado.",
    }
