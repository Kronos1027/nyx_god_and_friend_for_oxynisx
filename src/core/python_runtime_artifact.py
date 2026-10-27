"""Immutable bytes of a prepared CPython 3.11 Windows runtime for LPAC."""

from dataclasses import dataclass
from pathlib import Path

from core.project_snapshot import ProjectSnapshot, SnapshotLimits


@dataclass(frozen=True)
class PythonRuntimeArtifact:
    snapshot: ProjectSnapshot
    origin: str
    label: str = "CPython 3.11 Windows (declarado)"

    def __post_init__(self):
        if type(self.snapshot) is not ProjectSnapshot:
            raise ValueError("Snapshot de runtime inválido.")
        names = {item.name.casefold() for item in self.snapshot.files}
        required = {"python.exe", "python311.dll", "lib/encodings/__init__.py"}
        if not required <= names:
            raise ValueError("Runtime CPython 3.11 incompleto.")
        if any(name.endswith("._pth") or name == "pyvenv.cfg" for name in names):
            raise ValueError("Redirecionamento de caminhos do runtime não permitido.")
        if type(self.origin) is not str or not self.origin.strip() or len(self.origin) > 2048:
            raise ValueError("Origem declarada do runtime inválida.")
        if type(self.label) is not str or not self.label.strip() or len(self.label) > 120:
            raise ValueError("Identificação declarada do runtime inválida.")

    @classmethod
    def capture(cls, directory, *, cancelled=lambda: False):
        directory = Path(directory).absolute()
        snapshot = ProjectSnapshot.capture(directory, cancelled=cancelled, limits=SnapshotLimits(
            files=2048, entries=16384, bytes=128 * 1024 * 1024,
            file_bytes=32 * 1024 * 1024, depth=16, seconds=30))
        return cls(snapshot, str(directory))

    def review(self):
        return {"origin_declared": self.origin, "label_declared": self.label,
                "snapshot": self.snapshot.manifest(), "authenticity_verified": False}
