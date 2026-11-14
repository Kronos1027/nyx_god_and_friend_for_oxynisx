"""Bounded, source-backed measurements for Nyx local-model experiments.

Ollama durations are *nanoseconds*, not milliseconds. This module deliberately
stores no prompts, model answers, file contents, paths, or personal metadata.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Mapping, Sequence

_TIME_KEYS = ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")
_COUNT_KEYS = ("prompt_eval_count", "prompt_eval_cached_count", "eval_count")
_MAX_METRIC = 10**17


def generation_metrics(provider: Mapping) -> dict:
    """Extract only numeric Ollama usage values; reject booleans/invalid metrics."""
    if not isinstance(provider, dict):
        return {}
    clean = {}
    for name in (*_TIME_KEYS, *_COUNT_KEYS):
        value = provider.get(name)
        if type(value) is int and 0 <= value <= _MAX_METRIC:
            clean[name + ("_ns" if name in _TIME_KEYS else "")] = value
    ns = clean.get("eval_duration_ns", 0)
    n = clean.get("eval_count", 0)
    clean["output_tokens_per_second"] = round(n * 1_000_000_000 / ns, 3) if ns else None
    return clean


def summarize_trials(trials: Sequence[Mapping]) -> dict:
    """Aggregate verified goal outcomes, not self-reported model success.

    The comparison is descriptive; small samples do not establish superiority.
    """
    if not isinstance(trials, (list, tuple)):
        raise ValueError("trials deve ser uma lista")
    groups = defaultdict(list)
    for trial in trials:
        if not isinstance(trial, dict) or trial.get("variant") not in ("baseline", "goal_gate"):
            raise ValueError("variante de benchmark inválida")
        if type(trial.get("verified")) is not bool:
            raise ValueError("resultado deve ser bool independente")
        groups[trial["variant"]].append(trial)
    result = {"sample_size": len(trials), "variants": {}, "paired_delta_pp": None,
              "interpretation": "experimental_small_sample_not_proof"}
    for variant in ("baseline", "goal_gate"):
        rows = groups[variant]
        elapsed = [float(x["elapsed_seconds"]) for x in rows
                   if type(x.get("elapsed_seconds")) in (int, float)
                   and 0 <= x["elapsed_seconds"] < 86_400]
        rates = [float(y["output_tokens_per_second"]) for x in rows for y in x.get("generations", [])
                 if type(y.get("output_tokens_per_second")) in (int, float)
                 and 0 < y["output_tokens_per_second"] < 100000]
        result["variants"][variant] = {
            "tasks": len(rows),
            "verified_goals": sum(row["verified"] for row in rows),
            "success_rate_pct": round(100 * sum(row["verified"] for row in rows) / len(rows), 2) if rows else None,
            "median_elapsed_seconds": round(median(elapsed), 3) if elapsed else None,
            "median_output_tokens_per_second": round(median(rates), 3) if rates else None,
        }
    pairs = defaultdict(dict)
    for trial in trials:
        key = (trial.get("case"), trial.get("repeat"))
        pairs[key][trial["variant"]] = trial["verified"]
    matched = [d for d in pairs.values() if set(d) == {"baseline", "goal_gate"}]
    result["matched_pairs"] = len(matched)
    if matched:
        result["paired_delta_pp"] = round(
            100 * sum(int(d["goal_gate"]) - int(d["baseline"]) for d in matched) / len(matched), 2
        )
    return result
