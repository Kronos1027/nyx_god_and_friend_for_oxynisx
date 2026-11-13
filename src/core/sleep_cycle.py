"""Nyx: opt-in, CPU-only memory rehearsal when the computer is idle.

This is *not* model training or conscious dreaming. Only explicit user notes
are rehearsed; untrusted research, conversations and tool output are excluded.
No network, subprocess, model allocation or background thread is created.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GIB = 1024**3
MIN_AVAILABLE_RAM = 3 * GIB
MIN_IDLE_SECONDS = 120
MAX_NOTES_PER_CYCLE = 24
MAX_NOTE_CHARS = 1200
MAX_CARDS = 256
# Conservative rejection: do not rehearse possible credentials or identifiers.
_PRIVATE = re.compile(
    r"\b(?:senha|password|passphrase|token|secret|segredo|api[_ -]?key|"
    r"chave privada|private key|cpf|rg|cart[aã]o|cvv|iban|pix|"
    r"authorization|bearer|access[_ -]?key)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SleepResult:
    state: str
    reason: str
    created: int = 0
    inspected: int = 0


class SleepCycle:
    """Small, reversible rehearsal index layered on Nyx's existing SQLite DB.

    The source facts table is never written or rewritten by this component.
    Output cards are *rehearsal material*, not newly verified beliefs.
    """

    def __init__(self, memory_db: Path | str, clock: Callable[[], float] = time.time):
        self.path = Path(memory_db)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sleep_config (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
            db.execute("INSERT OR IGNORE INTO sleep_config VALUES ('enabled', 0)")
            db.execute("""CREATE TABLE IF NOT EXISTS sleep_cards (
                digest TEXT PRIMARY KEY, fact_key TEXT NOT NULL, source_hash TEXT NOT NULL,
                question TEXT NOT NULL, answer TEXT NOT NULL, created REAL NOT NULL)
            """)
            db.execute("CREATE INDEX IF NOT EXISTS sleep_cards_fact ON sleep_cards(fact_key)")
            db.execute("""CREATE TABLE IF NOT EXISTS sleep_runs (
                id INTEGER PRIMARY KEY, at REAL NOT NULL, state TEXT NOT NULL,
                reason TEXT NOT NULL, created INTEGER NOT NULL)
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=3.0)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enabled(self) -> bool:
        with self._connect() as db:
            return db.execute("SELECT value FROM sleep_config WHERE key='enabled'").fetchone()[0] == 1

    def set_enabled(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("Ativação precisa ser verdadeira ou falsa")
        with self._connect() as db:
            db.execute("UPDATE sleep_config SET value=? WHERE key='enabled'", (int(enabled),))

    def status(self) -> dict:
        with self._connect() as db:
            cards = db.execute("SELECT count(*) FROM sleep_cards").fetchone()[0]
            last = db.execute(
                "SELECT at, state, reason, created FROM sleep_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {"enabled": self.enabled(), "cards": cards, "last_run": dict(last) if last else None}

    def cards(self, limit: int = 10) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Limite de cards deve estar entre 1 e 50")
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT fact_key,question,answer,created FROM sleep_cards "
                "ORDER BY created DESC,digest LIMIT ?", (limit,)
            )]

    def delete_card(self, fact_key: str) -> int:
        """Forget derived material; source facts are managed by Nyx memory UI."""
        with self._connect() as db:
            return db.execute("DELETE FROM sleep_cards WHERE fact_key=?", (fact_key,)).rowcount

    def run_once(
        self, *, available_ram_bytes: int | None, idle_seconds: float,
        busy: bool = False, cancelled: Callable[[], bool] = lambda: False,
    ) -> SleepResult:
        if not self.enabled():
            return SleepResult("skipped", "disabled")
        if busy or idle_seconds < MIN_IDLE_SECONDS:
            return SleepResult("skipped", "not_idle")
        if type(available_ram_bytes) is not int or available_ram_bytes < MIN_AVAILABLE_RAM:
            return SleepResult("skipped", "memory_pressure_or_unknown")
        if cancelled():
            return SleepResult("skipped", "cancelled")
        created = inspected = 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='facts'"
            ).fetchone()
            if not exists:
                return SleepResult("skipped", "no_memory_facts")
            # Explicitly remembered user notes only; no inferred, system, or external text.
            rows = db.execute(
                "SELECT key,value FROM facts WHERE category='user_notes' "
                "ORDER BY updated_at DESC,key LIMIT ?", (MAX_NOTES_PER_CYCLE,)
            ).fetchall()
            for row in rows:
                if cancelled():
                    # All-or-nothing: no partial training/rehearsal after cancellation.
                    db.rollback()
                    return SleepResult("skipped", "cancelled")
                inspected += 1
                key, value = row["key"], row["value"]
                if not value or len(value) > MAX_NOTE_CHARS or _PRIVATE.search(value):
                    continue
                # Digest links card to the exact source fact and supports revision.
                source_hash = hashlib.sha256((key + "\0" + value).encode()).hexdigest()
                old = db.execute(
                    "SELECT source_hash FROM sleep_cards WHERE fact_key=?", (key,)
                ).fetchone()
                if old and old[0] == source_hash:
                    continue
                if old:
                    db.execute("DELETE FROM sleep_cards WHERE fact_key=?", (key,))
                digest = hashlib.sha256(("rehearsal\0" + source_hash).encode()).hexdigest()
                db.execute(
                    "INSERT INTO sleep_cards VALUES (?,?,?,?,?,?)",
                    (digest, key, source_hash,
                     "Qual informação o usuário pediu explicitamente para lembrar?", value,
                     self.clock()),
                )
                created += 1
            # Delete cards whose notes were edited, deleted, or recategorized.
            db.execute("""DELETE FROM sleep_cards WHERE NOT EXISTS (
                SELECT 1 FROM facts WHERE facts.key=sleep_cards.fact_key
                AND facts.category='user_notes'
            )""")
            # Invalidate old answers when the underlying fact was edited to sensitive text.
            for card in db.execute("SELECT fact_key,source_hash FROM sleep_cards").fetchall():
                source = db.execute(
                    "SELECT value FROM facts WHERE key=? AND category='user_notes'",
                    (card["fact_key"],)
                ).fetchone()
                if (source is None or not source[0] or len(source[0]) > MAX_NOTE_CHARS
                        or _PRIVATE.search(source[0]) or
                        hashlib.sha256((card["fact_key"] + "\0" + source[0]).encode()).hexdigest()
                        != card["source_hash"]):
                    db.execute("DELETE FROM sleep_cards WHERE fact_key=?", (card["fact_key"],))
            db.execute(
                "DELETE FROM sleep_cards WHERE digest NOT IN "
                "(SELECT digest FROM sleep_cards ORDER BY created DESC,digest LIMIT ?)",
                (MAX_CARDS,),
            )
            db.execute("INSERT INTO sleep_runs(at,state,reason,created) VALUES(?,?,?,?)",
                       (self.clock(), "completed", "rehearsal_only", created))
            db.execute("DELETE FROM sleep_runs WHERE id NOT IN "
                       "(SELECT id FROM sleep_runs ORDER BY id DESC LIMIT 50)")
        return SleepResult("completed", "rehearsal_only", created, inspected)
