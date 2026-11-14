"""Constant-space inference queue wait telemetry for performance research.

Records only bounded durations, not prompts, tool parameters, task IDs or
personal context. Called only while the scheduler's own lock is held.
"""
from __future__ import annotations

import math
from collections import deque
from statistics import median


class QueueWaitTracker:
    def __init__(self, capacity: int = 64):
        if type(capacity) is not int or not 8 <= capacity <= 256:
            raise ValueError("queue metrics capacity must be 8..256")
        self._samples: deque[float] = deque(maxlen=capacity)
        self.admitted = 0
        self.denied_full = 0
        self.wait_expired = 0
        self.cancelled = 0

    def granted(self, seconds: float) -> None:
        if type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0:
            self._samples.append(float(seconds))
        self.admitted += 1

    def report(self) -> dict:
        if self._samples:
            values = sorted(self._samples)
            p50 = round(median(values) * 1000, 2)
            p95 = round(values[math.ceil(len(values) * 0.95) - 1] * 1000, 2)
        else:
            p50 = p95 = None
        return {
            "admitted": self.admitted, "denied_full": self.denied_full,
            "wait_expired": self.wait_expired, "cancelled": self.cancelled,
            "wait_samples": len(self._samples),
            "wait_ms_p50": p50, "wait_ms_p95": p95,
        }
