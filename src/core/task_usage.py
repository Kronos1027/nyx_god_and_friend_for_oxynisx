"""Tiny, persistent usage counters for Nyx long-horizon tasks.

Only whitelisted numeric counters survive. Never retain prompts, completions,
API keys, tool arguments or free-form model text.
"""
from __future__ import annotations

MAX_COUNTER = 2**63 - 1
FIELDS = (
    "generation_attempts", "valid_json", "invalid_json", "prompt_tokens",
    "cached_prompt_tokens", "output_tokens", "total_duration_ns",
    "load_duration_ns", "eval_duration_ns",
)


def empty_usage() -> dict[str, int]:
    return {field: 0 for field in FIELDS}


def clean_usage(raw) -> dict[str, int]:
    result = empty_usage()
    if isinstance(raw, dict):
        for key in FIELDS:
            value = raw.get(key)
            if type(value) is int and 0 <= value <= MAX_COUNTER:
                result[key] = value
    return result


def accumulate_usage(current, attempts) -> dict[str, int]:
    stats = clean_usage(current)
    if not isinstance(attempts, (list, tuple)):
        return stats
    for row in attempts[:8]:  # Bounded even if a backend is malformed.
        if not isinstance(row, dict):
            continue
        stats["generation_attempts"] += 1
        if row.get("valid_json") is True:
            stats["valid_json"] += 1
        elif row.get("valid_json") is False:
            stats["invalid_json"] += 1
        for source, dest in (
            ("prompt_eval_count", "prompt_tokens"),
            ("prompt_eval_cached_count", "cached_prompt_tokens"),
            ("eval_count", "output_tokens"),
            ("total_duration_ns", "total_duration_ns"),
            ("load_duration_ns", "load_duration_ns"),
            ("eval_duration_ns", "eval_duration_ns"),
        ):
            value = row.get(source)
            if type(value) is int and 0 <= value <= MAX_COUNTER:
                stats[dest] = min(MAX_COUNTER, stats[dest] + value)
    stats["generation_attempts"] = min(MAX_COUNTER, stats["generation_attempts"])
    stats["valid_json"] = min(MAX_COUNTER, stats["valid_json"])
    stats["invalid_json"] = min(MAX_COUNTER, stats["invalid_json"])
    return stats


def usage_summary(raw) -> dict:
    data = clean_usage(raw)
    duration = data["eval_duration_ns"]
    return {**data, "generation_tokens_per_second": (
        round(data["output_tokens"] * 1_000_000_000 / duration, 3)
        if duration > 0 else None
    )}
