"""Reviewable MCP launch plans and one-use approval binding for LPAC only."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
from uuid import uuid4

from core.project_snapshot import ProjectSnapshot, SnapshotLimits, relative_name
from core.python_runtime_artifact import PythonRuntimeArtifact
from core.sandbox_journal import protect_directory
from core.windows_sandbox import run_lpac, validate_limits
from tools.mcp_client import MCPServerConfig


@dataclass(frozen=True)
class MCPLaunchPlan:
    server_id: str
    snapshot: ProjectSnapshot
    entrypoint: str
    tool_levels: tuple
    origin: str
    runtime: PythonRuntimeArtifact
    arguments: tuple = ()
    seconds: int = 60
    memory_mib: int = 256
    cpu_percent: int = 25
    processes: int = 2
    output_bytes: int = 65536

    def __post_init__(self):
        if type(self.runtime) is not PythonRuntimeArtifact:
            raise ValueError("A revisão precisa incluir os bytes do runtime Python.")
        if type(self.snapshot) is not ProjectSnapshot:
            raise ValueError("Snapshot MCP inválido.")
        if (not 1 <= len(self.snapshot.files) <= 64
                or sum(len(item.content) for item in self.snapshot.files) > 4 * 1024 * 1024
                or any(len(item.content) > 256 * 1024 or len(item.name.split("/")) > 8 for item in self.snapshot.files)
                or len(self.snapshot.skipped) > 1024):
            raise ValueError("Pacote MCP excede os limites de captura.")
        if (relative_name(self.entrypoint) != self.entrypoint or not self.entrypoint.endswith(".py")
                or self.entrypoint not in {item.name for item in self.snapshot.files}):
            raise ValueError("Entrada Python ausente ou inválida.")
        if type(self.tool_levels) is not tuple or any(type(pair) is not tuple or len(pair) != 2 for pair in self.tool_levels):
            raise ValueError("Política MCP deve ser imutável.")
        levels = dict(self.tool_levels)
        if len(levels) != len(self.tool_levels):
            raise ValueError("Ferramentas MCP duplicadas.")
        MCPServerConfig(self.server_id, ["isolated-python"], list(levels), levels)
        if (type(self.arguments) is not tuple or len(self.arguments) > 16
                or any(type(arg) is not str or len(arg) > 1024 or "\x00" in arg for arg in self.arguments)
                or sum(len(arg) for arg in self.arguments) > 4096):
            raise ValueError("Argumentos de servidor inválidos.")
        if type(self.origin) is not str or not self.origin.strip() or len(self.origin) > 2048:
            raise ValueError("Origem declarada inválida.")
        validate_limits(self.seconds, self.memory_mib, self.output_bytes, self.cpu_percent, self.processes)

    @classmethod
    def capture(cls, source, *, server_id, entrypoint, tool_levels, runtime, **limits):
        source = Path(source).absolute()
        snapshot = ProjectSnapshot.capture(source, limits=SnapshotLimits(
            files=64, entries=1024, bytes=4 * 1024 * 1024, file_bytes=256 * 1024, depth=8))
        return cls(server_id, snapshot, entrypoint, tuple(sorted(tool_levels.items())), str(source), runtime, **limits)

    def review(self):
        value = {"schema": 2, "server_id": self.server_id, "origin_declared": self.origin,
                 "snapshot": self.snapshot.manifest(), "entrypoint": self.entrypoint,
                 "runtime": self.runtime.review(),
                 "arguments": list(self.arguments), "tool_levels": dict(self.tool_levels),
                 "limits": {"seconds": self.seconds, "memory_mib": self.memory_mib,
                            "cpu_percent": self.cpu_percent, "processes": self.processes,
                            "output_bytes": self.output_bytes},
                 "execution": {"backend": "windows-lpac-prototype", "runtime": "approved-immutable-python",
                               "network": False, "capabilities": ["registryRead"],
                               "credentials": False, "host_execution": False}}
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        return {**value, "approval_digest": hashlib.sha256(encoded).hexdigest()}

    def client_config(self):
        """Derive the client policy from the same plan shown for launch approval."""
        levels = dict(self.tool_levels)
        return MCPServerConfig(self.server_id, ["lpac-snapshot", self.entrypoint], list(levels), levels)


class MCPApprovalGate:
    """Process-local, short-lived grants. UI must supply the digest it displayed.

    Not a tool for the model. This is not protection against malicious host code.
    Grants expire on process restart and never authorize individual tool calls.
    """

    def __init__(self, *, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._grants = {}

    def approve(self, plan, reviewed_digest, *, lifetime=60):
        if type(plan) is not MCPLaunchPlan or reviewed_digest != plan.review()["approval_digest"]:
            raise ValueError("Plano difere do conteúdo apresentado para aprovação.")
        if type(lifetime) is not int or not 1 <= lifetime <= 300:
            raise ValueError("Validade de aprovação inválida.")
        with self._lock:
            now = self._clock()
            self._grants = {key: value for key, value in self._grants.items() if value[1] > now}
            if len(self._grants) >= 32:
                raise ValueError("Limite de aprovações pendentes atingido.")
            token = secrets.token_urlsafe(32)
            self._grants[token] = (reviewed_digest, now + lifetime)
            return token

    def revoke(self, token):
        with self._lock:
            return self._grants.pop(token, None) is not None

    def consume(self, plan, token):
        with self._lock:
            grant = self._grants.pop(token, None)
            if (grant is None or self._clock() >= grant[1] or type(plan) is not MCPLaunchPlan
                    or grant[0] != plan.review()["approval_digest"]):
                raise PermissionError("Aprovação MCP ausente, vencida, consumida ou divergente.")


_BOOTSTRAP = """import runpy, sys
from pathlib import Path
entry = Path(sys.argv[1])
sys.argv = sys.argv[1:]
sys.path.insert(0, str(entry.parent))
runpy.run_path(str(entry), run_name='__main__')
"""


def run_approved_mcp(container, staging_parent, plan, gate, token, channel):
    """Trusted supervisor API; never reads candidate source after approval.

    Caller owns the profile and staging parent. Runtime and candidate bytes come
    only from the reviewed snapshots. Persistent recovery/UI remain pending.
    """
    if type(gate) is not MCPApprovalGate:
        raise TypeError("Gate MCP inválido.")
    gate.consume(plan, token)  # Before directory creation, ACL grants or execution.
    root = Path(staging_parent).absolute() / ("mcp-" + uuid4().hex)
    ProjectSnapshot(()).write_new_directory(root)
    protect_directory(root)
    source, work, runtime = root / "server", root / "work", root / "python"
    plan.snapshot.write_new_directory(source)
    plan.runtime.snapshot.write_new_directory(runtime)
    ProjectSnapshot(()).write_new_directory(work)
    container.grant(root, root)
    container.grant(root, work, writable=True)
    # Only the approved immutable bytes are materialized; original source paths
    # are provenance and never reopened. Candidate source is read-only in LPAC.
    result = run_lpac(container, Path(runtime) / "python.exe",
                      ["-I", "-S", "-X", "utf8", "-c", _BOOTSTRAP,
                       str(source.joinpath(*plan.entrypoint.split("/"))), *plan.arguments], work,
                      timeout=plan.seconds, memory_mib=plan.memory_mib,
                      cpu_percent=plan.cpu_percent, process_limit=plan.processes,
                      output_limit=plan.output_bytes, channel=channel, diagnostic_registry_read=True)
    return {**result, "approval_digest": plan.review()["approval_digest"], "staging": str(root)}
