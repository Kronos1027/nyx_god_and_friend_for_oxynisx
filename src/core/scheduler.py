"""Persistent, one-shot reminders. Scheduled entries never execute commands."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class ReminderScheduler:
    """Small SQLite reminder store safe to call from worker and UI threads."""

    MAX_PENDING = 100
    MAX_MESSAGE_CHARS = 500

    def __init__(self, database: Path | str = Path("data/nyx_schedule.db")) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    due_at TEXT NOT NULL,
                    message TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL
                )"""
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _parse_due(value: str) -> datetime:
        try:
            due = datetime.fromisoformat(value.strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe data e hora em formato ISO, por exemplo 2026-10-20T18:30") from exc
        if due.tzinfo is None:
            due = due.astimezone()
        return due.astimezone(timezone.utc)

    def add(self, due_at: str, message: str) -> dict[str, str]:
        message = str(message).strip()
        if not message or len(message) > self.MAX_MESSAGE_CHARS:
            raise ValueError(f"O lembrete deve ter de 1 a {self.MAX_MESSAGE_CHARS} caracteres.")
        due = self._parse_due(due_at)
        now = datetime.now(timezone.utc)
        if due <= now:
            raise ValueError("A data e hora precisam estar no futuro.")
        with self._connect() as conn:
            pending = conn.execute("SELECT COUNT(*) FROM reminders WHERE state='pending'").fetchone()[0]
            if pending >= self.MAX_PENDING:
                raise ValueError("A agenda atingiu o limite de lembretes pendentes.")
            reminder_id = uuid.uuid4().hex[:8]
            conn.execute(
                "INSERT INTO reminders(id,due_at,message,state,created_at) VALUES(?,?,?,'pending',?)",
                (reminder_id, due.isoformat(), message, now.isoformat()),
            )
        return {"id": reminder_id, "due_at": due.astimezone().isoformat(timespec="minutes"), "message": message}

    def list_pending(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,due_at,message FROM reminders WHERE state='pending' ORDER BY due_at LIMIT ?",
                (self.MAX_PENDING,),
            ).fetchall()
        return [
            {"id": r["id"], "due_at": datetime.fromisoformat(r["due_at"]).astimezone().isoformat(timespec="minutes"),
             "message": r["message"]}
            for r in rows
        ]

    def cancel(self, reminder_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE reminders SET state='cancelled' WHERE id=? AND state='pending'",
                (str(reminder_id).strip(),),
            )
            return cur.rowcount == 1

    def pop_due(self, now: datetime | None = None) -> list[dict[str, str]]:
        instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id,due_at,message FROM reminders WHERE state='pending' AND due_at<=? ORDER BY due_at",
                (instant.isoformat(),),
            ).fetchall()
            if rows:
                conn.executemany(
                    "UPDATE reminders SET state='fired' WHERE id=? AND state='pending'",
                    [(r["id"],) for r in rows],
                )
        return [{"id": r["id"], "message": r["message"], "due_at": r["due_at"]} for r in rows]
