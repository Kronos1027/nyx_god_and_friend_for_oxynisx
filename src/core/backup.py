"""Encrypted portable snapshots. The recovery key never enters the archive."""

from __future__ import annotations

import json
import errno
import os
import sqlite3
import tempfile
import threading
import time
import zipfile
import uuid
from pathlib import Path

from cryptography.fernet import Fernet


class BackupVault:
    # Explicit allowlist: no tokens, logs, screenshots, model weights or runtime paths.
    FILES = ("data/nyx_chats.db", "data/nyx_memory.db", "data/nyx_schedule.db", "data/nyx_evolution.db", "data/nyx_context.db", "data/nyx_tasks.db")
    MAX_BYTES = 32 * 1024 * 1024

    def __init__(self, root: Path):
        self.root = Path(root)
        self.directory = self.root / "data" / "backups"
        self.key_path = self.root / "data" / "backup-recovery.key"
        self._lock = threading.Lock()

    def _key(self) -> bytes:
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.key_path.exists():
            try:
                with self.key_path.open("xb") as stream:
                    stream.write(Fernet.generate_key())
            except FileExistsError:
                pass
        key = self.key_path.read_bytes()
        Fernet(key)  # Validate before creating any snapshot.
        return key

    def create(self) -> Path:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("Um backup já está em andamento")
        try:
            deadline = time.monotonic() + 20
            self.directory.mkdir(parents=True, exist_ok=True)
            cipher = Fernet(self._key())
            with tempfile.TemporaryDirectory(prefix="nyx-vault-") as directory:
                temp = Path(directory)
                archive = temp / "snapshot.zip"
                manifest = {"schema_version": 1, "files": []}
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                    total = 0
                    for relative in self.FILES:
                        source = self.root / relative
                        if not source.is_file():
                            continue
                        # SQLite online backup includes committed WAL data consistently.
                        target = temp / source.name
                        src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
                        dest = sqlite3.connect(target)
                        try:
                            def progress(status, remaining, total):
                                self._check_size(status, remaining, total)
                                if time.monotonic() > deadline:
                                    raise TimeoutError("Backup excedeu o prazo de 20 segundos")
                            src.backup(dest, pages=256, progress=progress, sleep=0.05)
                        finally:
                            src.close()
                            dest.close()
                        total += target.stat().st_size
                        if total > self.MAX_BYTES:
                            raise ValueError("Backup excede 32 MiB; revise a memória antes de continuar")
                        bundle.write(target, relative)
                        manifest["files"].append(relative)
                    bundle.writestr("manifest.json", json.dumps(manifest))
                encrypted = cipher.encrypt(archive.read_bytes())
            target = self.directory / "latest.nyxbackup"
            pending = target.with_suffix(".pending")
            pending.write_bytes(encrypted)
            try:
                os.replace(pending, target)
            except OSError as exc:
                if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
                    raise
                # Some Windows encrypted directories reject a same-directory rename.
                # Preserve the previous archive; publish only a fully verified new file.
                target = self.directory / f"snapshot-{uuid.uuid4().hex}.nyxbackup"
                with target.open("xb") as stream:
                    stream.write(encrypted)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.inspect(target, self._key())
                snapshots = sorted(
                    (p for p in self.directory.glob("snapshot-*.nyxbackup")
                     if len(p.stem) == 41 and all(c in "0123456789abcdef" for c in p.stem[9:]) and not p.is_symlink()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for old in snapshots[5:]:
                    if old != target:
                        try:
                            old.unlink()
                        except OSError:
                            pass
            return target
        finally:
            self._lock.release()

    def _check_size(self, status, remaining, total):
        if total * 4096 > self.MAX_BYTES:
            raise ValueError("Banco de dados excede o limite do backup")

    @classmethod
    def inspect(cls, path: Path, key: bytes) -> dict:
        import io

        if path.stat().st_size > cls.MAX_BYTES * 2:
            raise ValueError("Arquivo de backup grande demais")
        payload = Fernet(key).decrypt(path.read_bytes())
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if set(names) - set(cls.FILES) - {"manifest.json"}:
                raise ValueError("Backup contém caminhos não permitidos")
            if sum(item.file_size for item in archive.infolist()) > cls.MAX_BYTES + 4096:
                raise ValueError("Conteúdo do backup grande demais")
            return json.loads(archive.read("manifest.json"))

    @classmethod
    def restore_to_new_directory(cls, path: Path, key: bytes, destination: Path) -> dict:
        """Recover into a fresh directory; never overwrite a live SQLite database."""
        import io

        manifest = cls.inspect(path, key)
        if destination.exists():
            raise ValueError("Escolha uma pasta nova para recuperar o backup")
        destination.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(Fernet(key).decrypt(path.read_bytes()))) as archive:
            for name in archive.namelist():
                if name == "manifest.json":
                    continue
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
                db = sqlite3.connect(target)
                try:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Banco recuperado falhou na verificação de integridade")
                finally:
                    db.close()
        return manifest
