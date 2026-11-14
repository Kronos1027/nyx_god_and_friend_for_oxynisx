"""Read-only diagnostics use SQLite without acquiring the active agent lease."""
import importlib.util
import json
from pathlib import Path

import pytest

from core.task_diagnostics import read_task_diagnostics
from core.task_journal import TaskJournal


def save_task(journal, *, task_id="a", state="PLANNING_FINISHED", goal="private"):
    journal.save({
        "id": task_id,
        "state": state,
        "goal": goal,
        "steps": [{
            "tool": "write_file", "ok": True, "verified": True,
            "params": {"path": "C:/users/private/file.txt", "content": "PRIVATE DATA"},
            "output": "password=SUPERSENSITIVE",
        }],
        "goal_contract": {"kind": "file_bundle", "items": []},
        "goal_verdict": {"status": "VERIFIED", "reason": "all_files_verified"},
        "max_actions": 6, "timeout": 100, "spent": 1,
        "inflight": None, "uncertain": False,
    })


def test_can_inspect_active_journal_without_needing_lease(tmp_path):
    db = tmp_path / "tasks.sqlite"
    journal = TaskJournal(db)
    try:
        save_task(journal)
        result = read_task_diagnostics(db)
        assert result["inspected"] == 1
        assert result["verified_goals"] == 1
        assert result["total_verified_actions"] == 1
        assert result["states"] == {"GOAL_VERIFIED": 1}
        serial = json.dumps(result)
        for secret in ("SUPERSENSITIVE", "PRIVATE DATA", "C:/users/private", "private"):
            assert secret not in serial
    finally:
        journal.close()


def test_invalid_rows_are_counted_without_disclosing_content(tmp_path):
    db = tmp_path / "tasks.sqlite"
    journal = TaskJournal(db)
    try:
        save_task(journal, task_id="good", state="PAUSED")
        with journal._db() as conn:
            conn.execute("INSERT INTO tasks VALUES (?,?,?,?)",
                         ("invalid", "PLANNING_FINISHED", 1.0, "{malformed"))
        stats = read_task_diagnostics(db, limit=10)
        assert stats["inspected"] == 1
        assert stats["invalid_records"] == 1
        assert stats["states"] == {"IN_PROGRESS": 1}
    finally:
        journal.close()


def test_diagnostics_refuses_invalid_limit_and_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_task_diagnostics(tmp_path / "missing.db")
    for invalid in (-1, 0, 101, True):
        with pytest.raises(ValueError):
            read_task_diagnostics(tmp_path / "no.db", limit=invalid)


def test_cli_exports_only_safe_metrics(tmp_path, capsys):
    db = tmp_path / "tasks.sqlite"
    journal = TaskJournal(db)
    try:
        save_task(journal, goal="Secret project")
        spec = importlib.util.spec_from_file_location(
            "nyx_report_cli", Path(__file__).resolve().parents[1] / "tools" / "nyx_task_report.py",
        )
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        assert cli.main(["--db", str(db)]) == 0
        exported = capsys.readouterr().out
        assert "Secret project" not in exported
        assert "PRIVATE DATA" not in exported
        assert json.loads(exported)["inspected"] == 1
    finally:
        journal.close()
