"""Bounded inference queue telemetry with deterministic and concurrent tests."""
import threading
import time

import pytest

from core.inference_queue_metrics import QueueWaitTracker
from core.runtime_budget import (
    InferenceBusyError, InferenceCancelledError, InferenceGate
)


def test_wait_samples_are_bounded_and_percentiles_are_correct():
    counter = QueueWaitTracker(capacity=8)
    for i in range(12):
        counter.granted(i / 1000)
    stats = counter.report()
    assert stats["admitted"] == 12
    assert stats["wait_samples"] == 8
    assert stats["wait_ms_p50"] == 7.5
    assert stats["wait_ms_p95"] == 11
    assert "prompt" not in stats
    assert "content" not in stats


def test_wait_tracker_rejects_invalid_capacity():
    for size in (0, 1, 257, True, 8.3):
        with pytest.raises(ValueError):
            QueueWaitTracker(capacity=size)


def test_gate_telemetry_records_grants_and_queue_saturation():
    gate = InferenceGate(max_waiters=0)
    with gate.slot(timeout=1):
        with pytest.raises(InferenceBusyError, match="cheia"):
            with gate.slot(timeout=0.01):
                pass
        middle = gate.telemetry()
        assert middle["active"] == 1
        assert middle["denied_full"] == 1
        assert middle["admitted"] == 1
    stats = gate.telemetry()
    assert stats["waiting"] == 0 and stats["active"] == 0
    assert stats["wait_ms_p50"] is not None


def test_gate_tracks_expiration_and_cancel_without_leaking_requests():
    gate = InferenceGate(max_waiters=1)
    cancelled = threading.Event()
    outcomes = []

    def expire_worker():
        try:
            with gate.slot(timeout=0.03):
                outcomes.append("unexpected")
        except InferenceBusyError:
            outcomes.append("expired")

    def cancelled_worker():
        cancelled.set()
        try:
            with gate.slot(timeout=0.1, cancelled=cancelled.is_set):
                outcomes.append("unexpected")
        except InferenceCancelledError:
            outcomes.append("cancelled")

    with gate.slot(timeout=1):
        first = threading.Thread(target=expire_worker)
        second = threading.Thread(target=cancelled_worker)
        first.start()
        first.join(timeout=2)
        second.start()
        second.join(timeout=2)
        assert not first.is_alive() and not second.is_alive()
    stats = gate.telemetry()
    assert sorted(outcomes) == ["cancelled", "expired"]
    assert stats["wait_expired"] == 1
    assert stats["cancelled"] == 1
    assert stats["admitted"] == 1
    assert stats["waiting"] == 0


def test_queue_wait_histogram_has_no_background_polling():
    gate = InferenceGate(2)
    assert gate.telemetry()["wait_samples"] == 0
    with gate.slot(timeout=1):
        pass
    before = gate.telemetry()
    time.sleep(0.01)
    assert gate.telemetry() == before
