"""Persistent, inactive package inventory; imports never authorize execution."""

from pathlib import Path
import time
from uuid import uuid4

from core.project_store import ProjectStore
from core.skill_package import SkillPackage


class _PackageArtifacts(ProjectStore):
    MARKER = "Nyx inactive skill package artifacts v1\n"
    MAX_VERSIONS = 32
    VERSION_BYTES = 4 * 1024 * 1024
    MAX_BYTES = 64 * 1024 * 1024


class SkillPackageStore:
    def __init__(self, directory):
        self.artifacts = _PackageArtifacts(directory)
        with self.artifacts._db() as db:
            db.executescript("""
                CREATE UNIQUE INDEX IF NOT EXISTS package_names ON projects(title);
                CREATE TABLE IF NOT EXISTS package_origins(
                    project TEXT NOT NULL,version INTEGER NOT NULL,name TEXT NOT NULL,
                    description TEXT NOT NULL,origin TEXT NOT NULL,imported REAL NOT NULL,
                    PRIMARY KEY(project,version),
                    FOREIGN KEY(project,version) REFERENCES versions(project,number) ON DELETE CASCADE);
            """)

    def import_directory(self, directory, *, cancelled=lambda: False):
        source = Path(directory).absolute()
        package = SkillPackage.capture(source, cancelled=cancelled)
        if cancelled():
            raise ValueError("Importação cancelada antes de gravar o pacote.")
        return self.import_snapshot(package, origin=str(source))

    def import_snapshot(self, package, *, origin):
        if not isinstance(origin, str) or not origin.strip() or len(origin) > 2048:
            raise ValueError("Origem declarada inválida (até 2.048 caracteres).")
        if type(package) is not SkillPackage:
            raise ValueError("Pacote inválido.")
        checked = SkillPackage.from_snapshot(package.snapshot, package.metadata.name)
        if checked != package:
            raise ValueError("Metadados divergem dos bytes do pacote.")
        name = checked.metadata.name
        with self.artifacts._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM projects WHERE title=?", (name,)).fetchone()
            if row:
                identifier = row["id"]
            else:
                if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] >= self.artifacts.MAX_PROJECTS:
                    raise ValueError("Catálogo limitado a 64 pacotes.")
                identifier = uuid4().hex
                db.execute("INSERT INTO projects VALUES (?,?,?)", (identifier, name, time.time()))
            number = self.artifacts._save(db, identifier, checked.snapshot, "Importado; inativo")
            db.execute("INSERT INTO package_origins VALUES (?,?,?,?,?,?)",
                       (identifier, number, name, checked.metadata.description, origin, time.time()))
        return {"name": name, "version": number, "sha256": checked.snapshot.manifest()["sha256"],
                "state": "inactive", "validation": "structural_only"}

    def list_packages(self):
        # Metadata only: no resource blobs loaded until inspection is requested.
        with self.artifacts._db() as db:
            rows = db.execute("""
                SELECT p.name,p.version,p.description,p.origin,p.imported,v.digest,v.bytes
                FROM package_origins p JOIN versions v ON v.project=p.project AND v.number=p.version
                WHERE p.version=(SELECT MAX(q.version) FROM package_origins q WHERE q.project=p.project)
                ORDER BY p.name LIMIT 65
            """).fetchall()
            if len(rows) > 64:
                raise ValueError("Inventário excede 64 pacotes.")
            return [dict(row, state="inactive", validation="structural_only") for row in rows]

    def versions(self, name):
        with self.artifacts._db() as db:
            return [dict(row, state="inactive") for row in db.execute("""
                SELECT p.version,p.origin,p.imported,v.digest,v.bytes FROM package_origins p
                JOIN versions v ON v.project=p.project AND v.number=p.version
                WHERE p.name=? ORDER BY p.version DESC LIMIT 32
            """, (name,))]

    def load(self, name, version=None):
        if version is not None and (type(version) is not int or not 1 <= version <= 32):
            raise ValueError("Versão de pacote inválida.")
        with self.artifacts._db() as db:
            row = db.execute("""
                SELECT project,version,name,description FROM package_origins
                WHERE name=? AND (? IS NULL OR version=?) ORDER BY version DESC LIMIT 1
            """, (name, version, version)).fetchone()
        if row is None:
            raise ValueError("Pacote ou versão não encontrados.")
        snapshot = self.artifacts.load(row["project"], row["version"])
        package = SkillPackage.from_snapshot(snapshot, row["name"])
        if package.metadata.description != row["description"]:
            raise ValueError("Descrição do catálogo diverge do pacote.")
        return package

    def export(self, name, version, destination):
        return self.load(name, version).export_zip(destination)
