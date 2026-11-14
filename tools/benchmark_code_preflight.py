"""Synthetic cost of static preflight, without models/filesystem/test execution."""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tools.code_patch_preflight import check_edit_batch  # noqa: E402


def run(repeats=9) -> dict:
    if type(repeats) is not int or not 3 <= repeats <= 30:
        raise ValueError("repeats 3..30")
    sources = [
        SimpleNamespace(relative="app.py", content="\n".join(
            f"def compute_{i}(value): return value + {i}" for i in range(700)
        ) + "\n"),
        SimpleNamespace(relative="tests.py", content="\n".join(
            f"def test_{i}(): assert {i} == {i}" for i in range(700)
        ) + "\n"),
        SimpleNamespace(relative="settings.json", content=json.dumps(
            {f"option_{i}": {"enabled": True, "timeout": i} for i in range(1000)}
        )),
        SimpleNamespace(relative="pyproject.toml", content="\n".join(
            f"option_{i} = {i}" for i in range(1000)
        )),
        SimpleNamespace(relative="README.md", content="A project description."),
    ]
    times = []
    tracemalloc.start()
    try:
        for _ in range(repeats):
            start = time.perf_counter_ns()
            result = check_edit_batch(sources)
            times.append((time.perf_counter_ns() - start) / 1_000_000)
            assert sum(x["status"] == "PARSED" for x in result) == 4
            assert sum(x["status"] == "UNSCANNED" for x in result) == 1
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "benchmark": "nyx_static_preflight_synthetic_v1",
        "repeats": repeats,
        "files": len(sources), "parsed_files": 4,
        "median_ms": round(statistics.median(times), 3),
        "p95_ms": round(sorted(times)[__import__("math").ceil(len(times) * 0.95) - 1], 3),
        "peak_python_allocated_mib": round(peak / 1048576, 3),
        "limitations": "Syntax-only synthetic inputs; no real Qwen, pytest, disk or GPU.",
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
