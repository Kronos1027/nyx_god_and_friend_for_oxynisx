"""Bounded project artifacts, without executing project code or importing it.

Windows opens reject reparses atomically and enumerate through handles. Directory
handles deny delete-sharing while paths are traversed. File
handles additionally deny write-sharing, reject reparse points and hardlinks,
and supply the bytes actually hashed. This is a snapshot, not a filesystem quota
or a claim that the entire source tree was captured at one atomic instant.
"""

from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import unicodedata
import zipfile
from core.windows_files import ReparseRejected, windows_files


class SnapshotError(ValueError):
    pass


@dataclass(frozen=True)
class SnapshotLimits:
    files: int = 512
    entries: int = 4096
    bytes: int = 16 * 1024 * 1024
    file_bytes: int = 4 * 1024 * 1024
    depth: int = 16
    seconds: float = 10

    def __post_init__(self):
        for name, maximum in (
            ("files", 2048),
            ("entries", 16384),
            ("bytes", 128 * 1024 * 1024),
            ("file_bytes", 32 * 1024 * 1024),
            ("depth", 32),
        ):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise SnapshotError(f"Limite inválido: {name}")
        if not 0 < self.seconds <= 30:
            raise SnapshotError("Prazo inválido para copiar o projeto.")


EXCLUDED = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        ".local-deps",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".ssh",
        ".aws",
        ".azure",
        "credentials.json",
        "cookies.txt",
        "cookies.sqlite",
    }
)
RESERVED = re.compile(
    r"(?i)(?:con|prn|aux|nul|clock\$|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?\Z"
)


def component(name):
    if (
        not name
        or name in {".", ".."}
        or len(name) > 240
        or name[-1:] in {".", " "}
        or any(char in name for char in '/\\:<>"|?*')
        or any(unicodedata.category(char).startswith("C") for char in name)
        or RESERVED.fullmatch(name)
    ):
        raise SnapshotError("Nome de arquivo não portátil ou inseguro.")
    return name


def relative_name(name):
    if not isinstance(name, str) or not name or len(name) > 2048:
        raise SnapshotError("Caminho relativo inválido.")
    return "/".join(component(part) for part in name.split("/"))


def excluded(name):
    value = name.casefold()
    return (
        value in EXCLUDED
        or value == ".env"
        or value.startswith(".env.")
        or value.endswith((".pem", ".pfx", ".key"))
    )


@contextmanager
def pinned_directory(path):
    """Pin all ancestors before inspecting children; never resolve through links."""
    if os.name != "nt":
        raise SnapshotError("A cópia com proteção de caminhos exige o backend Windows.")
    path = Path(path).absolute()
    if os.name == "nt" and not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise SnapshotError("O snapshot exige um volume local; UNC/dispositivos são recusados.")
    with ExitStack() as stack:
        current = Path(path.anchor)
        for part in (None, *path.parts[1:]):
            if part is not None:
                current /= component(part)
            pinned = stack.enter_context(_directory_handle(current))
        yield pinned


@dataclass(frozen=True)
class PinnedDirectory:
    path: Path
    handle: object


@contextmanager
def _directory_handle(path, *, create=False):
    if os.name == "nt":
        import win32file

        try:
            handle = windows_files().open(path, directory=True, create=create)
        except ReparseRejected as error:
            raise SnapshotError(str(error)) from error
        try:
            attributes = win32file.GetFileInformationByHandle(handle)[0]
            if attributes & 0x400 or not attributes & 0x10:
                raise SnapshotError("Diretório redirecionado ou inválido.")
            yield PinnedDirectory(path, handle)
        finally:
            handle.Close()
    else:
        raise SnapshotError("Backend de diretórios Windows indisponível.")


@contextmanager
def regular_file(path, *, create=False):
    """Open while the caller holds the parent directories pinned."""
    if os.name == "nt":
        import msvcrt
        import win32file

        try:
            handle = windows_files().open(path, create=create)
        except ReparseRejected as error:
            raise SnapshotError(str(error)) from error
        try:
            info = win32file.GetFileInformationByHandle(handle)
            if (
                info[0] & (0x400 | 0x10 | 0x1000)
                or info[7] != 1
                or win32file.GetFileType(handle) != 1
            ):
                raise SnapshotError("Links, hardlinks e arquivos especiais não são copiados.")
            flags = os.O_BINARY | (os.O_WRONLY if create else os.O_RDONLY)
            native = handle.Detach()
            try:
                descriptor = msvcrt.open_osfhandle(native, flags)
            except BaseException:
                win32file.CloseHandle(native)
                raise
        finally:
            handle.Close()
    else:
        raise SnapshotError("Backend de arquivos Windows indisponível.")
    try:
        stream = os.fdopen(descriptor, "wb" if create else "rb")
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        yield stream


@dataclass(frozen=True)
class SnapshotFile:
    name: str
    content: bytes

    def __post_init__(self):
        relative_name(self.name)
        if type(self.content) is not bytes:
            raise SnapshotError("O conteúdo do snapshot deve ser imutável.")


@dataclass(frozen=True)
class ProjectSnapshot:
    files: tuple[SnapshotFile, ...]
    skipped: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.files) is not tuple or type(self.skipped) is not tuple:
            raise SnapshotError("O inventário deve ser imutável.")
        if len(self.files) > 2048 or len(self.skipped) > 16384:
            raise SnapshotError("Inventário excede o limite absoluto.")
        seen = set()
        spellings = {}
        total = 0
        for skipped in self.skipped:
            relative_name(skipped)
        for item in self.files:
            if type(item) is not SnapshotFile:
                raise SnapshotError("Entrada de snapshot inválida.")
            total += len(item.content)
            if total > 128 * 1024 * 1024 or len(item.content) > 32 * 1024 * 1024:
                raise SnapshotError("Snapshot excede o limite absoluto de bytes.")
            name = relative_name(item.name).casefold()
            if name in seen or any(
                name.startswith(previous + "/") or previous.startswith(name + "/")
                for previous in seen
            ):
                raise SnapshotError("Caminhos repetidos ou conflitantes no snapshot.")
            seen.add(name)
            parts = item.name.split("/")
            if len(parts) > 32:
                raise SnapshotError("Snapshot excede a profundidade absoluta.")
            for length in range(1, len(parts) + 1):
                spelling = "/".join(parts[:length])
                existing = spellings.setdefault(spelling.casefold(), spelling)
                if existing != spelling:
                    raise SnapshotError("Capitalização conflitante nos caminhos do snapshot.")

    @classmethod
    def capture(cls, source, *, limits=None, cancelled=lambda: False):
        limits = limits or SnapshotLimits()
        started, visited, total = time.monotonic(), 0, 0
        files, skipped = [], []

        def check():
            if cancelled():
                raise SnapshotError("Cópia do projeto cancelada.")
            if time.monotonic() - started > limits.seconds:
                raise SnapshotError("Prazo da cópia do projeto esgotado.")

        def walk(directory, prefix, depth):
            nonlocal visited, total
            check()
            if depth > limits.depth:
                raise SnapshotError("Projeto excede a profundidade permitida.")
            entries = []
            for entry in windows_files().entries(directory.handle):
                check()
                visited += 1
                if visited > limits.entries:
                    raise SnapshotError("Projeto excede o limite de entradas.")
                entries.append(entry)
            for filename, attributes in sorted(entries, key=lambda item: item[0].casefold()):
                check()
                name = prefix + component(filename)
                if excluded(filename):
                    skipped.append(name)
                    continue
                if attributes & 0x400:
                    raise SnapshotError("Links/reparse points não são copiados.")
                path = directory.path / filename
                if attributes & 0x10:
                    with _directory_handle(path) as child:
                        walk(child, name + "/", depth + 1)
                    continue
                if len(files) >= limits.files:
                    raise SnapshotError("Projeto excede o limite de arquivos.")
                with regular_file(path) as stream:
                    size = os.fstat(stream.fileno()).st_size
                    if size > limits.file_bytes or total + size > limits.bytes:
                        raise SnapshotError("Projeto excede o orçamento de bytes.")
                    data = bytearray()
                    while True:
                        check()
                        chunk = stream.read(
                            min(65536, limits.file_bytes - len(data) + 1, limits.bytes - total + 1)
                        )
                        if not chunk:
                            break
                        data.extend(chunk)
                        total += len(chunk)
                        if len(data) > limits.file_bytes or total > limits.bytes:
                            raise SnapshotError("Arquivo cresceu além do orçamento de bytes.")
                    files.append(SnapshotFile(name, bytes(data)))

        with pinned_directory(source) as root:
            walk(root, "", 0)
        return cls(tuple(files), tuple(skipped))

    def manifest(self):
        inventory = [
            {
                "path": item.name,
                "bytes": len(item.content),
                "sha256": hashlib.sha256(item.content).hexdigest(),
            }
            for item in self.files
        ]
        encoded = json.dumps(
            inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return {
            "version": 1,
            "files": inventory,
            "skipped": list(self.skipped),
            "bytes": sum(len(item.content) for item in self.files),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }

    def write_new_directory(self, destination):
        """Create a new staging tree. On failure keep the partial tree for review.

        Caller must own destination's parent and must not grant it to a running
        candidate. Never overwrite/reuse an existing directory or file.
        """
        destination = Path(destination).absolute()
        component(destination.name)
        with pinned_directory(destination.parent):
            with _directory_handle(destination, create=True), ExitStack() as stack:
                directories = {""}
                for item in self.files:
                    parts = item.name.split("/")
                    for count in range(1, len(parts)):
                        name = "/".join(parts[:count])
                        if name not in directories:
                            target = destination.joinpath(*parts[:count])
                            stack.enter_context(_directory_handle(target, create=True))
                            directories.add(name)
                    with regular_file(destination.joinpath(*parts), create=True) as stream:
                        stream.write(item.content)
                        stream.flush()
                        os.fsync(stream.fileno())
        return destination

    def export_zip(self, destination):
        """Write only immutable captured bytes to a new archive; no extraction."""
        destination = Path(destination).absolute()
        component(destination.name)
        with pinned_directory(destination.parent), regular_file(destination, create=True) as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                for item in self.files:
                    metadata = zipfile.ZipInfo(item.name)
                    metadata.external_attr = (stat.S_IFREG | 0o600) << 16
                    archive.writestr(metadata, item.content)
            stream.flush()
            os.fsync(stream.fileno())
