"""Reproducible CPU-only benchmark: exact same facts and bounded output.

Synthetic corpus only. Report latency, not full model inference/Windows UX.
Requires the optional compiled Rust wheel, never downloads models.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.kra13_hot_memory import bounded_fact_prompt as py_memory  # noqa: E402


def timed(fn, facts, query, budget, n):
    measures = []
    for _ in range(n):
        started = time.perf_counter()
        result = fn(facts, query, budget)
        measures.append(1000 * (time.perf_counter() - started))
        assert len(result) <= budget
    return {
        "median_ms": round(statistics.median(measures), 3),
        "min_ms": round(min(measures), 3),
        "max_ms": round(max(measures), 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", type=int, default=10_000)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if not 100 <= args.facts <= 100_000 or not 2 <= args.repeats <= 30:
        parser.error("facts 100..100000, repeats 2..30")
    import nyx_memory_native
    facts = {
        f"note_{i:06d}": f"Fato {i}: navegação estelar e memória de trabalho no Windows"
        for i in range(args.facts)
    }
    facts["security_policy"] = "Ações sensíveis exigem confirmação explícita."
    facts["user_name"] = "Teste local"
    query = "Windows navegação memória"
    native = nyx_memory_native.bounded_fact_prompt
    # Both implementations must produce exactly the same output.
    expected = py_memory(facts, query, 1700)
    assert native(facts, query, 1700) == expected
    py_memory(facts, query, 1700)
    native(facts, query, 1700)
    py_stats = timed(py_memory, facts, query, 1700, args.repeats)
    rust_stats = timed(native, facts, query, 1700, args.repeats)
    ratio = py_stats["median_ms"] / rust_stats["median_ms"] if rust_stats["median_ms"] else None
    print(json.dumps({
        "experiment": "nyx_memory_selector_native_v1",
        "facts": args.facts, "repeats": args.repeats,
        "output_parity": True, "python": py_stats, "rust": rust_stats,
        "relative_speed": round(ratio, 2) if ratio is not None else None,
        "measures": "CPU selection latency only, no GPU, Ollama or user data",
        "memory_usage_measured": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
