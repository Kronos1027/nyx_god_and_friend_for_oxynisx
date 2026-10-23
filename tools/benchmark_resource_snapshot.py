"""Measure real telemetry overhead without loading models or changing settings."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.runtime_budget import resource_snapshot  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.samples <= 1000:
        parser.error("--samples must be between 2 and 1000")
    durations = []
    for _ in range(args.samples):
        started = time.perf_counter()
        snapshot = resource_snapshot()
        durations.append((time.perf_counter() - started) * 1000)
    report = {"kind": "real_resource_telemetry", "samples_ms": durations,
              "mean_ms": statistics.mean(durations), "warm_mean_ms": statistics.mean(durations[1:]),
              "max_ms": max(durations), "last_snapshot": asdict(snapshot)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
