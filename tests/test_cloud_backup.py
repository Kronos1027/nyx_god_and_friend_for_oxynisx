import pytest
from cryptography.fernet import Fernet

from core.cloud_backup import BRANCH, REMOTE, CloudBackup


def test_cloud_stages_only_encrypted_snapshot_and_no_force(tmp_path, monkeypatch):
    snapshot = tmp_path / "latest.nyxbackup"
    snapshot.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"private"))
    backup = CloudBackup(tmp_path)
    calls = []

    def git(*args):
        calls.append(args)
        if args == ("remote", "get-url", "origin"):
            return REMOTE
        if args == ("branch", "--show-current"):
            return BRANCH
        if args == ("diff", "--cached", "--name-only"):
            return "latest.nyxbackup"
        if args == ("rev-parse", "HEAD"):
            return "abc123"
        return ""

    monkeypatch.setattr(backup, "_git", git)
    assert backup.upload(snapshot) == "abc123"
    assert ("add", "--", "latest.nyxbackup", "README.md") in calls
    assert not any("--force" in call for call in calls)
    assert not (backup.work / "backup-recovery.key").exists()


def test_cloud_rejects_plaintext_wrong_remote_and_unrelated_files(tmp_path, monkeypatch):
    snapshot = tmp_path / "latest.nyxbackup"
    snapshot.write_text("plaintext")
    backup = CloudBackup(tmp_path)
    with pytest.raises(ValueError):
        backup.upload(snapshot)
    snapshot.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"private"))
    (backup.work / ".git").mkdir(parents=True)
    monkeypatch.setattr(backup, "_git", lambda *args: "https://example.org")
    with pytest.raises(ValueError):
        backup.upload(snapshot)

    def git(*args):
        return {("remote", "get-url", "origin"): REMOTE,
                ("branch", "--show-current"): BRANCH,
                ("ls-files",): "backup-recovery.key"}.get(args, "")
    monkeypatch.setattr(backup, "_git", git)
    with pytest.raises(ValueError):
        backup.upload(snapshot)
