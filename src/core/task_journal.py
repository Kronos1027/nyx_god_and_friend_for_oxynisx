"""Bounded local checkpoints; an interrupted effect is never replayed."""
from contextlib import contextmanager
import json
import os
import re
from pathlib import Path
import sqlite3
import time


class TaskJournal:
    LIMIT = 200
    MAX_PAYLOAD = 131072
    TERMINAL = ("PLANNING_FINISHED", "CANCELLED", "FAILED")

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lease = self.path.with_suffix(".lock").open("a+b")
        self._lease.seek(0, 2)
        if self._lease.tell() == 0:
            self._lease.write(b"0")
            self._lease.flush()
        self._lease.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lease.close()
            self._lease = None
            raise RuntimeError("Outro runtime está usando o histórico de tarefas.") from exc
        try:
            with self._db() as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, state TEXT NOT NULL, updated REAL NOT NULL, payload TEXT NOT NULL)")
                for task_id, payload, updated in db.execute("SELECT id,payload,updated FROM tasks WHERE state NOT IN ('PLANNING_FINISHED','CANCELLED','FAILED','PAUSED','WAITING_REVIEW')").fetchall():
                    item = json.loads(payload)
                    item["pending"] = None  # approval is never carried across a restart
                    item["recovered"] = True
                    item["spent"] = min(item["timeout"], item["spent"] + max(0, time.time() - updated))
                    item["state"] = "WAITING_REVIEW" if item.get("inflight") or item.get("uncertain") else "PAUSED"
                    db.execute("UPDATE tasks SET state=?,payload=? WHERE id=?",
                               (item["state"], json.dumps(item, ensure_ascii=False), task_id))
        except Exception:
            self.close()
            raise

    def close(self):
        if self._lease is not None:
            self._lease.close()  # releases the OS lock, including on process exit
            self._lease = None

    @contextmanager
    def _db(self):
        if self._lease is None:
            raise RuntimeError("Histórico de tarefas fechado.")
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, item):
        clean = self._redact(item)
        clean["redacted"] = clean != item or item.get("redacted", False)
        payload = json.dumps(clean, ensure_ascii=False)
        if len(payload.encode("utf-8")) > self.MAX_PAYLOAD:
            raise ValueError("Checkpoint excede o limite; nenhuma próxima ação será iniciada.")
        with self._db() as db:
            exists = db.execute("SELECT 1 FROM tasks WHERE id=?", (item["id"],)).fetchone()
            count = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            if not exists and count >= self.LIMIT:
                oldest = db.execute("SELECT id FROM tasks WHERE state IN ('PLANNING_FINISHED','CANCELLED','FAILED') ORDER BY updated LIMIT 1").fetchone()
                if oldest is None:
                    raise ValueError("Histórico cheio de tarefas pendentes. Revise ou exclua uma antes de iniciar outra.")
                db.execute("DELETE FROM tasks WHERE id=?", oldest)
            db.execute("INSERT INTO tasks VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,updated=excluded.updated,payload=excluded.payload",
                       (item["id"], item["state"], time.time(), payload))

    @classmethod
    def _redact(cls, value):
        if isinstance(value, dict):
            return {key: "[protegido]" if re.search(r"password|senha|secret|token|cookie|authorization|api.?key", key, re.I)
                    else cls._redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        if isinstance(value, str):
            value = re.sub(r"(?i)\b(password|senha|token|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[protegido]", value)
            return re.sub(r"\bsk-[A-Za-z0-9_-]{16,}\b", "[protegido]", value)
        return value

    def get(self, task_id):
        with self._db() as db:
            row = db.execute("SELECT payload FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError("Tarefa não encontrada.")
        return json.loads(row[0])

    def list(self):
        with self._db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM tasks ORDER BY updated DESC LIMIT ?", (self.LIMIT,))]

    def delete(self, task_id):
        with self._db() as db:
            row = db.execute("SELECT state FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row and row[0] not in (*self.TERMINAL, "PAUSED", "WAITING_REVIEW", "RESOURCE_PRESSURE"):
                raise ValueError("Interrompa a tarefa antes de excluir seu histórico.")
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
