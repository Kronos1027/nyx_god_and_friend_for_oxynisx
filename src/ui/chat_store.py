"""Persistent desktop conversation library, separate from learned memories."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class ChatStore:
    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_by_chat ON messages(chat_id,id);
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=3)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, title: str = "Nova conversa") -> str:
        chat_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("INSERT INTO chats VALUES(?,?,?,?)", (chat_id, title[:100], now, now))
        return chat_id

    def list_chats(self, query: str = "") -> list[dict]:
        # Search both titles and message bodies, with literal LIKE characters.
        query = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{query}%"
        with self._connect() as connection:
            rows = connection.execute(r"""
                SELECT c.* FROM chats c
                WHERE c.title LIKE ? ESCAPE '\' OR EXISTS (
                    SELECT 1 FROM messages m WHERE m.chat_id=c.id AND m.content LIKE ? ESCAPE '\'
                ) ORDER BY c.updated_at DESC LIMIT 250
            """, (pattern, pattern)).fetchall()
        return [dict(row) for row in rows]

    def messages(self, chat_id: str, limit: int = 100) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT * FROM (SELECT * FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?)
                ORDER BY id
            """, (chat_id, min(250, max(1, limit)))).fetchall()
        return [dict(row) for row in rows]

    def append(self, chat_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant", "error"}:
            raise ValueError("Papel de mensagem inválido.")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO messages(chat_id,role,content,created_at) VALUES(?,?,?,?)",
                (chat_id, role, str(content)[:100_000], now),
            )
            connection.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_id))
            if role == "user":
                connection.execute(
                    "UPDATE chats SET title=? WHERE id=? AND title='Nova conversa'",
                    (str(content).replace("\n", " ")[:65], chat_id),
                )

    def rename(self, chat_id: str, title: str) -> None:
        if title.strip():
            with self._connect() as connection:
                connection.execute("UPDATE chats SET title=? WHERE id=?", (title.strip()[:100], chat_id))

    def delete(self, chat_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chats WHERE id=?", (chat_id,))
