"""Persistent local server settings. Saving never approves or launches code."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sqlite3

from core.mcp_launch import MCPLaunchPlan
from core.project_snapshot import relative_name
from core.python_runtime_artifact import PythonRuntimeArtifact
from core.sandbox_journal import protect_directory, reject_link
from core.windows_sandbox import validate_limits
from tools.mcp_client import MCPServerConfig


@dataclass(frozen=True)
class MCPServerDefinition:
    server_id: str
    source_directory: str
    runtime_directory: str
    entrypoint: str
    tool_levels: tuple = ()
    arguments: tuple = ()
    seconds: int = 60
    memory_mib: int = 256
    cpu_percent: int = 25
    processes: int = 2
    output_bytes: int = 65536

    def __post_init__(self):
        for path in (self.source_directory, self.runtime_directory):
            if (type(path) is not str or len(path) > 2048 or not re.match(r"^[A-Za-z]:[\\/]", path)
                    or "\x00" in path or ":" in path[2:] or ".." in re.split(r"[\\/]", path)):
                raise ValueError("Escolha um caminho Windows local absoluto.")
        if relative_name(self.entrypoint) != self.entrypoint or not self.entrypoint.endswith(".py"):
            raise ValueError("Entrada Python inválida.")
        if type(self.tool_levels) is not tuple or any(type(pair) is not tuple or len(pair) != 2 for pair in self.tool_levels):
            raise ValueError("Política MCP inválida.")
        levels = dict(self.tool_levels)
        if len(levels) != len(self.tool_levels):
            raise ValueError("Ferramentas repetidas.")
        MCPServerConfig(self.server_id, ["lpac-snapshot"], list(levels), levels)
        if (type(self.arguments) is not tuple or len(self.arguments) > 16
                or any(type(arg) is not str or len(arg) > 1024 or "\x00" in arg for arg in self.arguments)
                or sum(len(arg) for arg in self.arguments) > 4096):
            raise ValueError("Argumentos inválidos.")
        validate_limits(self.seconds, self.memory_mib, self.output_bytes, self.cpu_percent, self.processes)

    def prepare(self, *, cancelled=lambda: False):
        runtime = PythonRuntimeArtifact.capture(self.runtime_directory, cancelled=cancelled)
        if cancelled():
            raise ValueError("Preparação cancelada.")
        return MCPLaunchPlan.capture(self.source_directory, server_id=self.server_id,
            entrypoint=self.entrypoint, tool_levels=dict(self.tool_levels), runtime=runtime,
            arguments=self.arguments, seconds=self.seconds, memory_mib=self.memory_mib,
            cpu_percent=self.cpu_percent, processes=self.processes, output_bytes=self.output_bytes)


class MCPCatalog:
    MARKER = "Nyx MCP server settings v1\n"

    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        for path in (self.directory, *self.directory.parents):
            reject_link(path)
        self.directory.mkdir(parents=True, exist_ok=True)
        marker = self.directory / ".nyx-mcp-catalog"
        reject_link(marker)
        if marker.exists():
            if marker.stat().st_size > 100 or marker.read_text(encoding="utf-8") != self.MARKER:
                raise ValueError("Catálogo MCP não reconhecido.")
        elif any(self.directory.iterdir()):
            raise ValueError("Pasta não pertence ao catálogo MCP.")
        else:
            protect_directory(self.directory)
            marker.write_text(self.MARKER, encoding="utf-8")
        self.path = self.directory / "servers.sqlite3"
        for suffix in ("", "-journal", "-wal", "-shm"):
            reject_link(Path(str(self.path) + suffix))
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS servers(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, settings TEXT NOT NULL)")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA secure_delete=ON")
            size = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={8 * 1024 * 1024 // size}")
            with db:
                yield db
        finally:
            db.close()

    def save(self, definition, *, expected_revision=None):
        if type(definition) is not MCPServerDefinition:
            raise TypeError("Definição MCP inválida.")
        encoded = json.dumps(asdict(definition), ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > 16384:
            raise ValueError("Configuração MCP excede 16 KiB.")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM servers WHERE id=?", (definition.server_id,)).fetchone()
            revision = row[0] if row else None
            if revision != expected_revision or (expected_revision is not None and type(expected_revision) is not int):
                raise ValueError("Configuração mudou; recarregue antes de salvar.")
            if row is None and db.execute("SELECT COUNT(*) FROM servers").fetchone()[0] >= 64:
                raise ValueError("Catálogo limitado a 64 servidores.")
            revision = (revision or 0) + 1
            db.execute("INSERT OR REPLACE INTO servers VALUES (?,?,?)", (definition.server_id, revision, encoded))
        return revision

    def list_servers(self):
        with self._db() as db:
            return [dict(row, state="requires_review") for row in db.execute("SELECT id,revision FROM servers ORDER BY id LIMIT 64")]

    def load(self, server_id):
        with self._db() as db:
            row = db.execute("SELECT revision,settings FROM servers WHERE id=? AND length(settings)<=16384", (server_id,)).fetchone()
        if row is None:
            raise ValueError("Servidor ausente ou configuração excessiva.")
        values = json.loads(row["settings"])
        values["tool_levels"] = tuple(tuple(pair) for pair in values.get("tool_levels", []))
        values["arguments"] = tuple(values.get("arguments", []))
        definition = MCPServerDefinition(**values)
        if definition.server_id != server_id:
            raise ValueError("Identidade do servidor diverge do registro.")
        return definition, row["revision"]

    def delete(self, server_id, *, expected_revision):
        if type(expected_revision) is not int:
            raise ValueError("Revisão inválida.")
        with self._db() as db:
            cursor = db.execute("DELETE FROM servers WHERE id=? AND revision=?", (server_id, expected_revision))
            if cursor.rowcount != 1:
                raise ValueError("Configuração mudou ou já foi removida.")
