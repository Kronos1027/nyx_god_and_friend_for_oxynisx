import pytest
from cryptography.fernet import Fernet

from core.cloud_backup import BRANCH, REMOTE, CloudBackup


def test_cloud_stages_only_encrypted_snapshot_and_no_force(tmp_path, monkeypatch):
    snapshot = tmp_path / "latest.nyxbackup"
    snapshot.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"private"))
    backup = CloudBackup(tmp_path)
    monkeypatch.setattr(backup, "_assert_private_destination", lambda: None)
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
    monkeypatch.setattr(backup, "_assert_private_destination", lambda: None)
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



def test_cloud_rejects_public_destination_before_git_operations(tmp_path, monkeypatch):
    import subprocess
    snapshot = tmp_path / "latest.nyxbackup"
    snapshot.write_bytes(Fernet(Fernet.generate_key()).encrypt(b"private"))
    backup = CloudBackup(tmp_path)
    seen = []
    class Result:
        returncode = 0
        stdout = "false\n"
    def fake(command, **kwargs):
        seen.append((command, kwargs))
        return Result()
    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(RuntimeError, match="repositório privado"):
        backup.upload(snapshot)
    assert not backup.work.exists()
    assert seen and seen[0][0][:4] == [
        "gh", "api", "--hostname", "github.com"
    ]
    assert "repos/Kronos1027/nyx_god_and_friend_for_oxynisx" in seen[0][0]


def test_cloud_fails_closed_without_gh_or_authenticated_visibility(tmp_path, monkeypatch):
    import subprocess
    backup = CloudBackup(tmp_path)
    def missing(*args, **kwargs):
        raise FileNotFoundError("gh")
    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="nuvem bloqueado"):
        backup._assert_private_destination()


def test_private_authenticated_visibility_can_proceed_without_secrets_in_output(tmp_path, monkeypatch):
    import subprocess
    backup = CloudBackup(tmp_path)
    class Result:
        returncode = 0
        stdout = "true\n"
    def fake(command, **kwargs):
        assert "token" not in str(command).lower()
        assert kwargs["capture_output"] is True
        return Result()
    monkeypatch.setattr(subprocess, "run", fake)
    backup._assert_private_destination()
