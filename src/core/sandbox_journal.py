"""Host-only ownership journal for ephemeral Nyx AppContainer profiles.

Reserve before creation; remove a reservation only after OS cleanup succeeds.
A lifetime OS lease prevents recovery from touching another live supervisor.
This journal never accepts filesystem paths or commands from sandbox output.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import uuid4

MARKER = "Nyx sandbox ownership journal v1\n"
NAME = re.compile(r"Nyx\.Sandbox\.[0-9a-f]{32}\Z")


def reject_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("O diário do sandbox não aceita links/reparse points.")
    if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
        raise ValueError("O diário do sandbox não aceita hardlinks.")


def protect_directory(path):
    if os.name != "nt":
        path.chmod(0o700)
        return
    import win32api
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
    try:
        user = win32security.GetTokenInformation(token, 1)[0]
    finally:
        token.Close()
    acl = win32security.ACL()
    for sid in (user, win32security.CreateWellKnownSid(win32security.WinLocalSystemSid)):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 3, 0x1F01FF, sid)
    win32security.SetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.PROTECTED_DACL_SECURITY_INFORMATION | 4,
        None,
        None,
        acl,
        None,
    )


class SandboxJournal:
    LIMIT = 128

    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        self._lease = None
        self._active = set()
        for path in (self.directory, *self.directory.parents):
            reject_link(path)
        self.directory.mkdir(parents=True, exist_ok=True)
        marker = self.directory / ".nyx-sandbox-journal"
        reject_link(marker)
        if marker.exists():
            if marker.stat().st_size > 100 or marker.read_text(encoding="utf-8") != MARKER:
                raise ValueError("Identificação do diário do sandbox inválida.")
        elif any(self.directory.iterdir()):
            raise ValueError("A pasta não pertence ao diário de sandbox da Nyx.")
        else:
            protect_directory(self.directory)
            marker.write_text(MARKER, encoding="utf-8")
        self.path = self.directory / "profiles.sqlite3"
        for name in (
            "profiles.lock",
            "profiles.sqlite3",
            "profiles.sqlite3-journal",
            "profiles.sqlite3-wal",
            "profiles.sqlite3-shm",
        ):
            reject_link(self.directory / name)
        self._lease = (self.directory / "profiles.lock").open("a+b")
        try:
            if self._lease.seek(0, 2) == 0:
                self._lease.write(b"0")
                self._lease.flush()
            self._lease.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self._db() as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, storage TEXT)"
                )
                if "storage" not in [row[1] for row in db.execute("PRAGMA table_info(profiles)")]:
                    db.execute("ALTER TABLE profiles ADD COLUMN storage TEXT")
        except Exception:
            self.close()
            raise

    @contextmanager
    def _db(self):
        if self._lease is None:
            raise RuntimeError("Diário de sandbox fechado.")
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def pending(self):
        with self._db() as db:
            rows = db.execute("SELECT name FROM profiles LIMIT ?", (self.LIMIT + 1,)).fetchall()
        if len(rows) > self.LIMIT or any(not NAME.fullmatch(row[0]) for row in rows):
            raise ValueError("Diário de sandbox inválido; nenhuma limpeza foi iniciada.")
        return [row[0] for row in rows]

    def reserve(self):
        if len(self.pending()) >= self.LIMIT:
            raise RuntimeError("Há perfis pendentes demais para iniciar outro sandbox.")
        name = "Nyx.Sandbox." + uuid4().hex
        with self._db() as db:
            db.execute("INSERT INTO profiles(name) VALUES (?)", (name,))
        self._active.add(name)
        return name

    def storage(self, name, value=None):
        if name not in self.pending():
            raise ValueError("Perfil não pertence ao diário.")
        with self._db() as db:
            if value is not None:
                db.execute("UPDATE profiles SET storage=? WHERE name=?", (str(value), name))
            return db.execute("SELECT storage FROM profiles WHERE name=?", (name,)).fetchone()[0]

    def forget(self, name):
        if not NAME.fullmatch(name) or name not in self.pending():
            raise ValueError("Perfil não pertence ao diário.")
        with self._db() as db:
            db.execute("DELETE FROM profiles WHERE name=?", (name,))
        self._active.discard(name)

    def recover(self, delete_profile):
        # Validate the entire inventory before the first external deletion.
        pending = self.pending()
        recovered = []
        for name in pending:
            if name in self._active:
                continue
            delete_profile(name)  # exceptions preserve the reservation for retry
            self.forget(name)
            recovered.append(name)
        return recovered

    def close(self):
        if self._lease is not None:
            self._lease.close()
            self._lease = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
