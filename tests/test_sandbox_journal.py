import sqlite3

import pytest

from core.sandbox_journal import SandboxJournal


def test_recovery_requires_lease_and_never_removes_live_reservations(tmp_path):
    called = []
    with SandboxJournal(tmp_path / "journal") as journal:
        name = journal.reserve()
        assert journal.recover(called.append) == []
        with pytest.raises(OSError):
            SandboxJournal(journal.directory)
        assert called == []
    with SandboxJournal(tmp_path / "journal") as reopened:
        assert reopened.recover(called.append) == [name]
        assert called == [name]
        assert reopened.pending() == []


def test_cleanup_failure_keeps_reservation_for_retry(tmp_path):
    with SandboxJournal(tmp_path / "journal") as journal:
        name = journal.reserve()
    with SandboxJournal(tmp_path / "journal") as reopened:

        def failure(_):
            raise OSError("OS cleanup failed")

        with pytest.raises(OSError, match="OS cleanup failed"):
            reopened.recover(failure)
        assert reopened.pending() == [name]
    with SandboxJournal(tmp_path / "journal") as retried:
        assert retried.recover(lambda _: None) == [name]


def test_invalid_inventory_is_rejected_before_any_delete(tmp_path):
    with SandboxJournal(tmp_path / "journal") as journal:
        journal.reserve()
        with sqlite3.connect(journal.path) as db:
            db.execute("INSERT INTO profiles(name) VALUES (?)", ("Some.Other.App",))
    called = []
    with SandboxJournal(tmp_path / "journal") as reopened:
        with pytest.raises(ValueError, match="nenhuma limpeza"):
            reopened.recover(called.append)
        assert called == []


def test_unowned_directory_and_linked_database_are_rejected(tmp_path):
    import os

    directory = tmp_path / "unowned"
    directory.mkdir()
    (directory / "user.txt").write_text("preserve")
    with pytest.raises(ValueError, match="não pertence"):
        SandboxJournal(directory)
    assert (directory / "user.txt").read_text() == "preserve"
    with SandboxJournal(tmp_path / "owned") as journal:
        path = journal.path
    os.link(path, tmp_path / "database-alias")
    with pytest.raises(ValueError, match="hardlinks"):
        SandboxJournal(tmp_path / "owned")
