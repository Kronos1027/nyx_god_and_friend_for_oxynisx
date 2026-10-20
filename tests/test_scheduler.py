from datetime import datetime, timedelta, timezone

import pytest

from core.scheduler import ReminderScheduler
from tools.reminder_tool import make_reminder_tool_func


def test_reminder_persists_lists_fires_once_and_cancels(tmp_path):
    database = tmp_path / "reminders.sqlite3"
    scheduler = ReminderScheduler(database)
    due = datetime.now(timezone.utc) + timedelta(minutes=5)
    item = scheduler.add(due.isoformat(), "Enviar o relatório")

    reopened = ReminderScheduler(database)
    assert reopened.list_pending()[0]["id"] == item["id"]
    assert reopened.pop_due(now=due - timedelta(seconds=1)) == []
    fired = reopened.pop_due(now=due + timedelta(seconds=1))
    assert fired[0]["message"] == "Enviar o relatório"
    assert reopened.pop_due(now=due + timedelta(days=1)) == []
    assert reopened.cancel(item["id"]) is False


def test_reminder_rejects_past_dates_and_cancellation(tmp_path):
    scheduler = ReminderScheduler(tmp_path / "reminders.sqlite3")
    with pytest.raises(ValueError, match="futuro"):
        scheduler.add((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), "Tarefa")

    due = datetime.now(timezone.utc) + timedelta(minutes=10)
    item = scheduler.add(due.isoformat(), "Telefonar")
    assert scheduler.cancel(item["id"]) is True
    assert scheduler.list_pending() == []


def test_reminder_tool_operations(tmp_path):
    scheduler = ReminderScheduler(tmp_path / "reminders.sqlite3")
    tool = make_reminder_tool_func(scheduler)
    due = datetime.now(timezone.utc) + timedelta(minutes=3)
    result = tool({"operation": "add", "due_at": due.isoformat(), "message": "Pausa"})
    assert result.ok is True
    assert tool({"operation": "list"}).meta["count"] == 1
    assert tool({"operation": "cancel", "id": result.meta["id"]}).ok is True
    assert tool({"operation": "unknown"}).ok is False
