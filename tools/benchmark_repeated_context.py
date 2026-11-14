"""Deterministic CPU-only benchmark for repeated memory prompt selection.

Measures selection/cache overhead, not LLM throughput. No files, network,
Ollama, credentials, or private facts. Run on a fresh Python process.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.context_prompt_cache import ContextPromptCache  # noqa: E402
from core.kra13_hot_memory import bounded_fact_prompt as python_selector  # noqa: E402
from core.memory import CoreMemory  # noqa: E402


def measure(facts_count=10_000, trials=9):
    if type(facts_count) is not int or not 100 <= facts_count <= 100_000:
        raise ValueError("facts_count 100..100000")
    if type(trials) is not int or not 3 <= trials <= 30:
        raise ValueError("trials 3..30")
    # Only measure derived-view selection; CoreMemory integration with SQLite
    # and invalidation is separately covered by pytest.
    facts = {f"fact_{i:05d}": f"Informação astronômica de navegação {i}"
             for i in range(facts_count)}
    facts["security_policy"] = "Ações sensíveis exigem confirmação"
    facts["user_name"] = "Usuário fictício"

    core = CoreMemory.__new__(CoreMemory)
    core._facts = facts
    core._prompt_cache = ContextPromptCache()
    core._fact_lock = threading.RLock()
    query = "navegação astronomia"
    expected = python_selector(facts, query, 1700)
    assert core.format_prompt_block(query) == expected
    cold = []
    warm = []
    for _ in range(trials):
        start = time.perf_counter()
        assert python_selector(facts, query, 1700) == expected
        cold.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        assert core.format_prompt_block(query) == expected
        warm.append((time.perf_counter() - start) * 1000)
    baseline = statistics.median(cold)
    cached = statistics.median(warm)
    return {
        "benchmark": "nyx_repeated_context_v1",
        "facts": facts_count, "trials": trials, "output_parity": True,
        "baseline_ms_median": round(baseline, 4),
        "cached_ms_median": round(cached, 4),
        "relative_speed": round(baseline / cached, 2) if cached else None,
        "cache": core._prompt_cache.stats(),
        "limitations": "Repeated exact query only. No SQLite, Qwen, disk or GPU timings.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", type=int, default=10_000)
    parser.add_argument("--trials", type=int, default=9)
    opts = parser.parse_args()
    print(json.dumps(measure(opts.facts, opts.trials), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
