"""Exclusive ownership of profiles created specifically for Nyx.

This isolates cookies from the personal browser; it is not an OS sandbox.
The browser supplies its normal OS credential encryption. No cookie import API.
"""
from pathlib import Path
import os
import re
import shutil
import stat
import subprocess
import tempfile

MARKER = "Nyx isolated browser profile v1\n"


def _redirected(path):
    try:
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def _protect_profile(path):
    if os.name != "nt":
        path.chmod(0o700)
        return
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True, text=True, timeout=5, creationflags=flags, check=True)
    sid = re.search(r"S-1-5-\d+(?:-\d+)+", identity.stdout)
    if not sid:
        raise ValueError("Não foi possível identificar a conta Windows para proteger o perfil.")
    subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                    f"*{sid.group()}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
                   capture_output=True, timeout=5, creationflags=flags, check=True)


class BrowserProfile:
    def __init__(self, persistent_dir: Path | None = None):
        self.temporary = persistent_dir is None
        self.path = Path(tempfile.mkdtemp(prefix="nyx-browser-")) if self.temporary else Path(persistent_dir).absolute()
        self._lock = None
        try:
            if _redirected(self.path) or any(_redirected(p) for p in self.path.parents):
                raise ValueError("O perfil isolado não pode atravessar links simbólicos.")
            self.path.mkdir(parents=True, exist_ok=True)
            marker = self.path / ".nyx-profile"
            if marker.exists():
                if _redirected(marker) or marker.stat().st_size > 100 or marker.read_text(encoding="utf-8") != MARKER:
                    raise ValueError("Identificação do perfil Nyx inválida.")
            elif any(self.path.iterdir()):
                raise ValueError("Pasta existente não pertence à Nyx; nenhum perfil pessoal será aberto ou importado.")
            else:
                _protect_profile(self.path)
                marker.write_text(MARKER, encoding="utf-8")
            lock_path = self.path / ".nyx-lock"
            if _redirected(lock_path):
                raise ValueError("Arquivo de bloqueio inválido.")
            self._lock = lock_path.open("a+b")
            self._lock.seek(0, 2)
            if self._lock.tell() == 0:
                self._lock.write(b"0")
                self._lock.flush()
            self._lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError("Este perfil Nyx já está em uso por outra sessão.") from exc
        except Exception:
            self.close()
            raise

    def close(self):
        if self._lock is not None:
            # Closing releases the OS lock even after a failed acquisition.
            self._lock.close()
            self._lock = None
        if self.temporary:
            shutil.rmtree(self.path, ignore_errors=True)
