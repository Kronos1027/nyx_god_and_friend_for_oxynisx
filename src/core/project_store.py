"""Bounded, immutable project versions; no project code is executed here."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from core.project_snapshot import ProjectSnapshot, SnapshotFile
from core.sandbox_journal import protect_directory, reject_link


class ProjectStore:
    MAX_PROJECTS = 64
    MAX_VERSIONS = 50
    MAX_BYTES = 128 * 1024 * 1024
    VERSION_BYTES = 16 * 1024 * 1024
    MARKER = "Nyx project versions v1\n"

    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        for path in (self.directory, *self.directory.parents):
            reject_link(path)
        self.directory.mkdir(parents=True, exist_ok=True)
        marker = self.directory / ".nyx-project-store"
        reject_link(marker)
        if marker.exists():
            if marker.stat().st_size > 100 or marker.read_text(encoding="utf-8") != self.MARKER:
                raise ValueError("Identificação do catálogo de projetos inválida.")
        elif any(self.directory.iterdir()):
            raise ValueError("A pasta existente não pertence ao catálogo de projetos.")
        else:
            protect_directory(self.directory)
            marker.write_text(self.MARKER, encoding="utf-8")
        self.path = self.directory / "projects.sqlite3"
        for suffix in ("", "-wal", "-shm", "-journal"):
            reject_link(Path(str(self.path) + suffix))
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,title TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS versions(project TEXT NOT NULL,number INTEGER NOT NULL,
                    created REAL NOT NULL,note TEXT NOT NULL,digest TEXT NOT NULL,bytes INTEGER NOT NULL,
                    manifest TEXT NOT NULL,PRIMARY KEY(project,number),
                    FOREIGN KEY(project) REFERENCES projects(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS files(project TEXT NOT NULL,version INTEGER NOT NULL,
                    position INTEGER NOT NULL,name TEXT NOT NULL,content BLOB NOT NULL,
                    PRIMARY KEY(project,version,position),
                    FOREIGN KEY(project,version) REFERENCES versions(project,number) ON DELETE CASCADE);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA secure_delete=ON")
            # Physical DB ceiling includes metadata and unused pages, not just blobs.
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={192*1024*1024 // page_size}")
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _text(value, length):
        if not isinstance(value, str) or not value.strip() or len(value) > length:
            raise ValueError("Nome ou descrição inválidos.")
        return value.strip()

    def create(self, title, snapshot):
        title = self._text(title, 120)
        identifier = uuid4().hex
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] >= self.MAX_PROJECTS:
                raise ValueError("Catálogo cheio; revise os projetos antes de criar outro.")
            db.execute("INSERT INTO projects VALUES (?,?,?)", (identifier, title, time.time()))
            self._save(db, identifier, snapshot, "Versão inicial")
        return identifier

    def save(self, identifier, snapshot, note="Nova versão"):
        note = self._text(note, 500)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._save(db, identifier, snapshot, note)

    def _save(self, db, identifier, snapshot, note):
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (identifier,)).fetchone():
            raise ValueError("Projeto não encontrado.")
        if type(snapshot) is not ProjectSnapshot:
            raise ValueError("Snapshot inválido.")
        manifest = snapshot.manifest()
        if len(snapshot.files) > 512 or manifest["bytes"] > self.VERSION_BYTES:
            raise ValueError(f"Versão excede 512 arquivos ou {self.VERSION_BYTES} bytes.")
        count, number = db.execute(
            "SELECT COUNT(*),COALESCE(MAX(number),0)+1 FROM versions WHERE project=?", (identifier,)
        ).fetchone()
        if count >= self.MAX_VERSIONS:
            raise ValueError(f"Catálogo atingiu {self.MAX_VERSIONS} versões; exporte e revise o histórico.")
        used = db.execute("SELECT COALESCE(SUM(bytes),0) FROM versions").fetchone()[0]
        if used + manifest["bytes"] > self.MAX_BYTES:
            raise ValueError(f"Catálogo atingiu o orçamento de {self.MAX_BYTES} bytes.")
        encoded = json.dumps(manifest, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 1024 * 1024:
            raise ValueError("Manifesto excede 1 MiB.")
        db.execute(
            "INSERT INTO versions VALUES (?,?,?,?,?,?,?)",
            (identifier, number, time.time(), note, manifest["sha256"], manifest["bytes"], encoded),
        )
        db.executemany(
            "INSERT INTO files VALUES (?,?,?,?,?)",
            [
                (identifier, number, index, item.name, item.content)
                for index, item in enumerate(snapshot.files)
            ],
        )
        return number

    def projects(self):
        with self._db() as db:
            return [
                dict(row)
                for row in db.execute("SELECT id,title,created FROM projects ORDER BY created DESC")
            ]

    def versions(self, identifier):
        with self._db() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT number,created,note,digest,bytes FROM versions WHERE project=? ORDER BY number DESC",
                    (identifier,),
                )
            ]

    def load(self, identifier, number):
        with self._db() as db:
            db.execute("BEGIN")
            count, total, largest = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(length(content)),0),COALESCE(MAX(length(content)),0) "
                "FROM files WHERE project=? AND version=?",
                (identifier, number),
            ).fetchone()
            if count > 512 or total > self.VERSION_BYTES or largest > self.VERSION_BYTES:
                raise ValueError("Inventário persistido excede limites.")
            size = db.execute(
                "SELECT length(CAST(manifest AS BLOB)) FROM versions WHERE project=? AND number=?",
                (identifier, number),
            ).fetchone()
            if size and size[0] > 1024 * 1024:
                raise ValueError("Manifesto persistido excede limites.")
            record = db.execute(
                "SELECT digest,manifest,bytes FROM versions WHERE project=? AND number=?",
                (identifier, number),
            ).fetchone()
            if not record:
                raise ValueError("Versão não encontrada.")
            if not 0 <= record["bytes"] <= self.VERSION_BYTES:
                raise ValueError("Tamanho persistido inválido.")
            rows = db.execute(
                "SELECT name,content FROM files WHERE project=? AND version=? ORDER BY position",
                (identifier, number),
            ).fetchmany(513)
            if len(rows) > 512 or sum(len(row["content"]) for row in rows) > self.VERSION_BYTES:
                raise ValueError("Inventário persistido excede limites.")
            manifest = json.loads(record["manifest"])
            snapshot = ProjectSnapshot(
                tuple(SnapshotFile(row["name"], row["content"]) for row in rows),
                tuple(manifest.get("skipped", [])),
            )
            if snapshot.manifest() != manifest or manifest["sha256"] != record["digest"]:
                raise ValueError("Integridade da versão não confere; exportação bloqueada.")
            return snapshot

    def restore(self, identifier, number):
        snapshot = self.load(identifier, number)
        return self.save(identifier, snapshot, f"Restauração da versão {number}")

    def delete(self, identifier):
        with self._db() as db:
            db.execute("DELETE FROM projects WHERE id=?", (identifier,))
