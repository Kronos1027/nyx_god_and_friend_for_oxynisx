"""Data-minimized Nyx audit records.

Audit must explain *what kind* of operation happened, but should not persist
prompts, completions, tool payloads, file paths or secret-bearing observations.
The task journal remains the separate, permission-scoped source of detailed
step evidence and has its own redaction/recovery checks.
"""
from __future__ import annotations

from core.task_journal import TaskJournal

_OMITTED = "[conteúdo omitido por privacidade]"
_PRIVATE_TEXT_FIELDS = frozenset((
    "user_input", "llm_raw", "result_output", "raw_response",
    "prompt", "response_raw", "goal", "message_content",
))
_PRIVATE_PARAMS_FIELDS = frozenset(("params", "action_params", "arguments"))
_PRIVATE_LIST_FIELDS = frozenset(("steps", "observations", "history"))
_MAX_LIST = 48


def _shape(value):
    """Small, non-reversible description of structure, not its content."""
    if isinstance(value, dict):
        return {"type": "object", "fields": min(len(value), 64)}
    if isinstance(value, list):
        return {"type": "array", "items": min(len(value), _MAX_LIST)}
    if isinstance(value, str):
        return {"type": "text", "characters": min(len(value), 100_000)}
    if value is None:
        return {"type": "none"}
    return {"type": type(value).__name__[:32]}


def safe_audit_payload(event: str, payload: dict) -> dict:
    """Reduce sensitive fields without changing event names/status booleans."""
    safe = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            continue
        if key in _PRIVATE_TEXT_FIELDS:
            safe[key] = _OMITTED
            safe[f"{key}_size"] = _shape(value)
        elif key in _PRIVATE_PARAMS_FIELDS or key in _PRIVATE_LIST_FIELDS:
            safe[key] = _shape(value)
        elif key in {"subtasks", "agents"}:
            safe[key] = _shape(value)
        elif key == "pending":
            safe[key] = _shape(value)
        elif key == "output" and isinstance(value, str):
            safe[key] = _shape(value)
        elif key == "detail" and event == "security":
            safe[key] = _OMITTED
        else:
            # Legacy sanitizer also redacts credentials in nested dictionaries,
            # headers and plain text that contains password=/token= etc.
            safe[key] = TaskJournal._redact(value)
    return safe
