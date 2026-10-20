"""Agent tool for creating, listing, and cancelling local reminders."""

from __future__ import annotations

import json

from core.scheduler import ReminderScheduler
from tools.registry import ToolResult


def make_reminder_tool_func(scheduler: ReminderScheduler):
    def run(params: dict) -> ToolResult:
        operation = params.get("operation", "list")
        if operation == "add":
            item = scheduler.add(params.get("due_at", ""), params.get("message", ""))
            return ToolResult(ok=True, output=f"Lembrete {item['id']} salvo para {item['due_at']}: {item['message']}", meta=item)
        if operation == "list":
            items = scheduler.list_pending()
            return ToolResult(ok=True, output=json.dumps(items, ensure_ascii=False), meta={"count": len(items)})
        if operation == "cancel":
            reminder_id = str(params.get("id", ""))
            if scheduler.cancel(reminder_id):
                return ToolResult(ok=True, output=f"Lembrete {reminder_id} cancelado.")
            return ToolResult(ok=False, error=f"Lembrete pendente não encontrado: {reminder_id}")
        return ToolResult(ok=False, error="Operação inválida. Use add, list ou cancel.")

    return run
