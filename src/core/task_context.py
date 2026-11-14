"""Compact long-running task evidence while retaining recent action detail.

Pure data transformation; no model calls, permission changes, or external effects.
Produces valid JSON; external observations are explicitly untrusted data.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Mapping, Sequence


def _small(value, n: int):
    s = str(value) if value is not None else ""
    return s[:n]


def _recent_item(step: Mapping, number: int, preview_chars: int) -> dict:
    from core.task_journal import TaskJournal
    # Redact private values before including them in the next model prompt.
    params = json.dumps(TaskJournal._redact(step.get("params", {})),
                        ensure_ascii=False, separators=(",", ":"), default=str)
    out = str(TaskJournal._redact(str(step.get("output") or "")))
    return {
        "n": number,
        "tool": _small(step.get("tool", "?"), 48),
        "params": params[:96],
        "params_truncated": len(params) > 96,
        "params_sha12": hashlib.sha256(params.encode("utf-8")).hexdigest()[:12],
        "ok": bool(step.get("ok")),
        "verified": step.get("verified") is True,
        "preview": out[:preview_chars],
        "preview_truncated": len(out) > preview_chars or bool(step.get("output_truncated")),
    }


def compact_task_ledger(
    steps: Sequence[Mapping], *, max_chars: int = 4000, recent_limit: int = 8,
) -> str:
    """Condense older actions, preserve last actions and early failure identities."""
    if type(max_chars) is not int or max_chars < 1200 or max_chars > 12000:
        raise ValueError("max_chars must be 1200..12000")
    if type(recent_limit) is not int or not 1 <= recent_limit <= 16:
        raise ValueError("recent_limit must be 1..16")
    recent = steps[-recent_limit:]
    old = steps[:-recent_limit]
    by_tool = Counter(_small(s.get("tool", "?"), 48) for s in old)
    failures = [
        {"step": i + 1, "tool": _small(s.get("tool"), 48)}
        for i, s in enumerate(old) if not s.get("ok") or s.get("verified") is not True
    ]
    common = {
        "format": "nyx_compacted_ledger_v1",
        "authority": "untrusted_tool_observations",
        "total_steps": len(steps),
        "older": {
            "count": len(old),
            "verified": sum(bool(s.get("ok")) and s.get("verified") is True for s in old),
            "failed_or_unverified": len(failures),
            "by_tool": dict(sorted(by_tool.items())[:25]),
            "earlier_failures": failures[:8],
            "earlier_failure_count_omitted": max(0, len(failures) - 8),
        },
    }
    # Reduce preview, then number of detailed records as a bounded fallback.
    for count in range(len(recent), 0, -1):
        for chars in (220, 120, 60, 0):
            payload = dict(common)
            payload["recent"] = [
                _recent_item(step, len(steps) - len(recent) + i + 1, chars)
                for i, step in enumerate(recent[-count:], len(recent) - count)
            ]
            payload["recent_omitted"] = len(recent) - count
            text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if len(text) <= max_chars:
                return text
    # Very small bound and very long tool names: retain aggregate rather than
    # truncate serialized JSON or invent an observation.
    return json.dumps(
        {"format": "nyx_compacted_ledger_v1", "authority": "untrusted_tool_observations",
         "total_steps": len(steps), "older": {"count": len(steps),
                                             "verified": sum(bool(s.get("ok")) and
                                                             s.get("verified") is True for s in steps),
                                             "failed_or_unverified": sum(not s.get("ok") or
                                                                         s.get("verified") is not True for s in steps)},
         "recent": [], "recent_omitted": len(steps)},
        ensure_ascii=False, separators=(",", ":"),
    )
