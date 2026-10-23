import threading
import time

import pytest

from core.resource_governor import ResourceGovernor, ResourcePolicy, OperatingMode
from core.runtime_budget import (
    GIB, MIB, ResourceSnapshot, WorkPriority, InferenceGate,
    InferenceCancelledError, InferenceBusyError,
)


HEALTHY = ResourceSnapshot(8 * GIB, 12 * GIB, 6 * GIB, 10, 16 * GIB)


def test_pressure_recovers_with_fresh_telemetry():
    governor = ResourceGovernor()
    governor.set_mode("working")
    assert not governor.evaluate(ResourceSnapshot(GIB - 1, None, None)).allowed
    assert governor.mode == OperatingMode.PRESSURE
    assert governor.evaluate(HEALTHY).allowed
    assert governor.mode == OperatingMode.WORKING


def test_commit_exhaustion_blocks_despite_available_physical_ram():
    governor = ResourceGovernor()
    snapshot = ResourceSnapshot(8 * GIB, None, None, 0, 16 * GIB, 31 * GIB, 31 * GIB + MIB)
    assert not governor.evaluate(snapshot).allowed
    assert governor.mode == OperatingMode.PRESSURE


def test_optional_work_respects_focus_cpu_memory_queue_and_unknowns():
    governor = ResourceGovernor()
    assert governor.evaluate(HEALTHY, WorkPriority.BACKGROUND).allowed
    for snapshot in (
        ResourceSnapshot(2 * GIB, None, None, 10),
        ResourceSnapshot(8 * GIB, None, None, 90),
        ResourceSnapshot(None, None, None),
    ):
        assert not governor.evaluate(snapshot, WorkPriority.BACKGROUND).allowed
    assert not governor.evaluate(HEALTHY, WorkPriority.BACKGROUND, queued=1).allowed
    governor.set_mode("idle", focused=True)
    assert not governor.evaluate(HEALTHY, WorkPriority.BACKGROUND).allowed
    assert governor.evaluate(HEALTHY, WorkPriority.INTERACTIVE).allowed


def test_sleep_suspends_inference_and_latency_throttles_optional_work():
    governor = ResourceGovernor()
    governor.set_mode("sleep")
    assert not governor.evaluate(HEALTHY).allowed
    governor.set_mode("conversation")
    assert governor.evaluate(HEALTHY).allowed
    governor.set_mode("idle")
    governor.record_latency(40)
    assert not governor.evaluate(HEALTHY, WorkPriority.BACKGROUND).allowed
    assert governor.evaluate(HEALTHY).allowed


def test_custom_reserves_persist_and_are_enforced(tmp_path):
    governor = ResourceGovernor(ResourcePolicy(ram_reserve_bytes=4 * GIB, background_ram_bytes=5 * GIB))
    path = tmp_path / "resource-policy.json"
    governor.save_policy(path)
    restored = ResourceGovernor()
    restored.load_policy(path)
    assert not restored.evaluate(ResourceSnapshot(3 * GIB, None, None)).allowed
    assert restored.telemetry()["policy"] == governor.telemetry()["policy"]


@pytest.mark.parametrize("params", [
    {"ram_reserve_bytes": MIB}, {"vram_reserve_bytes": 0},
    {"background_cpu_percent": float("nan")}, {"background_latency_seconds": float("inf")},
    {"background_cpu_percent": 101}, {"background_ram_bytes": GIB - 1},
])
def test_invalid_resource_policies_are_rejected(params):
    with pytest.raises(ValueError):
        ResourcePolicy(**params)


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert predicate()


def test_interactive_precedes_queued_background():
    gate = InferenceGate(2)
    order = []
    def run(priority):
        with gate.slot(timeout=2, priority=priority):
            order.append(priority)
    with gate.slot():
        background = threading.Thread(target=run, args=(WorkPriority.BACKGROUND,))
        background.start()
        wait_for(lambda: gate.telemetry()["waiting"] == 1)
        # A second background job cannot consume the reserved interactive slot.
        with pytest.raises(InferenceBusyError):
            with gate.slot(priority=WorkPriority.BACKGROUND):
                pass
        interactive = threading.Thread(target=run, args=(WorkPriority.INTERACTIVE,))
        interactive.start()
        wait_for(lambda: gate.telemetry()["waiting"] == 2)
    background.join(2)
    interactive.join(2)
    assert order == [WorkPriority.INTERACTIVE, WorkPriority.BACKGROUND]
    assert not gate.telemetry()["active"]


def test_cancelled_waiter_is_removed_without_entering():
    gate = InferenceGate(2)
    cancelled = threading.Event()
    outcomes = []
    def wait():
        try:
            with gate.slot(cancelled=cancelled.is_set):
                outcomes.append("entered")
        except InferenceCancelledError:
            outcomes.append("cancelled")
    with gate.slot():
        worker = threading.Thread(target=wait)
        worker.start()
        wait_for(lambda: gate.telemetry()["waiting"] == 1)
        cancelled.set()
        worker.join(1)
        assert not worker.is_alive()
        assert gate.telemetry()["waiting"] == 0
    assert outcomes == ["cancelled"]


def test_pre_cancelled_request_cannot_take_free_slot():
    gate = InferenceGate()
    with pytest.raises(InferenceCancelledError):
        with gate.slot(cancelled=lambda: True):
            pytest.fail("cancelled work started")
    assert gate.telemetry()["active"] == 0
