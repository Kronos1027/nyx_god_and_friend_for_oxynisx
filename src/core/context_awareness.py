"""Permission-gated event collection. No screen capture or polling daemon."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3
import time

SENSORS = {"own_tasks": True, "research": True, "resources": True,
           "processes": False, "folders": False, "browser": False, "active_window": False}
EVENT_KINDS = {"task_failed", "task_complete", "research_found", "resource_pressure",
               "process_exited", "project_changed", "download_complete", "deadline"}


def safe_excerpt(value, limit=160):
    value = re.sub(r"(?i)(password|senha|token|api[_-]?key|secret)\s*[:=]\s*\S+", r"\1=[redigido]", str(value))
    value = re.sub(r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]+", "[redigido]", value)
    return " ".join(value.split())[:limit]


class ContextAwarenessEngine:
    MAX_EVENTS = 500

    def __init__(self, database: Path, clock=time.time):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._last_collection = {}
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sensors (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS context_events (
                    id TEXT PRIMARY KEY, sensor TEXT NOT NULL, kind TEXT NOT NULL,
                    title TEXT NOT NULL, source TEXT NOT NULL, created REAL NOT NULL,
                    expires REAL NOT NULL, offered INTEGER NOT NULL DEFAULT 0,
                    resolved INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS observation_access (
                    id INTEGER PRIMARY KEY, sensor TEXT, at REAL, outcome TEXT
                );
                CREATE TABLE IF NOT EXISTS initiatives (
                    id INTEGER PRIMARY KEY, event_id TEXT, offered REAL, day TEXT,
                    message TEXT, reason TEXT, response TEXT DEFAULT 'pending'
                );
            """)
            db.executemany("INSERT OR IGNORE INTO sensors VALUES (?,?)", SENSORS.items())

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def permissions(self):
        with self.connect() as db:
            return {row["name"]: bool(row["enabled"]) for row in db.execute("SELECT * FROM sensors")}

    def set_permission(self, sensor, enabled):
        if sensor not in SENSORS or type(enabled) is not bool:
            raise ValueError("Permissão de observação inválida")
        with self.connect() as db:
            db.execute("UPDATE sensors SET enabled=? WHERE name=?", (enabled, sensor))
            if not enabled:
                db.execute("DELETE FROM context_events WHERE sensor=?", (sensor,))
            self._audit(db, sensor, "enabled" if enabled else "disabled")

    def _audit(self, db, sensor, outcome):
        db.execute("INSERT INTO observation_access(sensor,at,outcome) VALUES (?,?,?)", (sensor, self.clock(), outcome))
        db.execute("DELETE FROM observation_access WHERE id NOT IN (SELECT id FROM observation_access ORDER BY id DESC LIMIT 500)")

    def collect(self, sensor, collector, *, under_load=False):
        """Check permission BEFORE invoking a sensor; never collect then discard."""
        if not self.permissions().get(sensor, False) or under_load:
            return []
        now = self.clock()
        if now - self._last_collection.get(sensor, float("-inf")) < 5:
            return []
        self._last_collection[sensor] = now
        try:
            from itertools import islice
            results = [self.emit(sensor=sensor, **event) for event in islice(collector(), 32)]
            with self.connect() as db:
                self._audit(db, sensor, "collected")
            return [result for result in results if result]
        except Exception:
            with self.connect() as db:
                self._audit(db, sensor, "failed")
            raise

    def emit(self, sensor, kind, key, title, source="", ttl=3600):
        if sensor not in SENSORS or kind not in EVENT_KINDS or not str(key):
            raise ValueError("Evento de contexto inválido")
        now = self.clock()
        event_id = hashlib.sha256(f"{sensor}:{kind}:{key}".encode()).hexdigest()[:32]
        ttl = max(30, min(float(ttl), 86400))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            permission = db.execute("SELECT enabled FROM sensors WHERE name=?", (sensor,)).fetchone()
            if not permission or not permission[0]:
                return None
            db.execute("DELETE FROM context_events WHERE expires<?", (now,))
            result = db.execute("INSERT OR IGNORE INTO context_events VALUES (?,?,?,?,?,?,?,0,0)",
                                (event_id, sensor, kind, safe_excerpt(title), safe_excerpt(source), now, now + ttl))
            if not result.rowcount:
                return None
            self._audit(db, sensor, "event_received")
            db.execute("DELETE FROM context_events WHERE id NOT IN (SELECT id FROM context_events ORDER BY created DESC, rowid DESC LIMIT ?)", (self.MAX_EVENTS,))
        return event_id

    def resolve(self, event_id):
        with self.connect() as db:
            db.execute("UPDATE context_events SET resolved=1 WHERE id=?", (event_id,))

    def access_history(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM observation_access ORDER BY id DESC LIMIT 100")]

    def clear(self):
        with self.connect() as db:
            db.execute("DELETE FROM context_events")
            db.execute("DELETE FROM initiatives")
            db.execute("DELETE FROM observation_access")
