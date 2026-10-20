import sqlite3

import pytest
from cryptography.fernet import Fernet, InvalidToken

from core.backup import BackupVault


def test_encrypted_backup_restores_committed_wal_without_keys_or_secrets(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    db = sqlite3.connect(data / "nyx_chats.db")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE chats (message TEXT)")
    db.execute("INSERT INTO chats VALUES ('private text')")
    db.commit()
    (tmp_path / ".env").write_text("SECRET=excluded")
    vault = BackupVault(tmp_path)
    snapshot = vault.create()
    assert b"private text" not in snapshot.read_bytes()
    manifest = vault.inspect(snapshot, vault.key_path.read_bytes())
    assert manifest["files"] == ["data/nyx_chats.db"]
    destination = tmp_path / "recovered"
    vault.restore_to_new_directory(snapshot, vault.key_path.read_bytes(), destination)
    with sqlite3.connect(destination / "data/nyx_chats.db") as restored:
        assert restored.execute("SELECT message FROM chats").fetchone()[0] == "private text"
    with pytest.raises(ValueError):
        vault.restore_to_new_directory(snapshot, vault.key_path.read_bytes(), destination)
    db.close()


def test_wrong_key_tampering_and_limits_rejected(tmp_path):
    vault = BackupVault(tmp_path)
    snapshot = vault.create()
    with pytest.raises(InvalidToken):
        vault.inspect(snapshot, Fernet.generate_key())
    snapshot.write_bytes(snapshot.read_bytes()[:-5] + b"wrong")
    with pytest.raises(InvalidToken):
        vault.inspect(snapshot, vault.key_path.read_bytes())


def test_concurrent_backup_is_bounded(tmp_path):
    vault = BackupVault(tmp_path)
    vault._lock.acquire()
    try:
        with pytest.raises(RuntimeError):
            vault.create()
    finally:
        vault._lock.release()
