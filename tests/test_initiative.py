from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.context_awareness import ContextAwarenessEngine
from core.initiative import ProactiveInteractionEngine, InitiativePreferences


@pytest.fixture
def engines(tmp_path):
    clock = [10000.0]
    context = ContextAwarenessEngine(tmp_path / "context.db", clock=lambda: clock[0])
    policy = ProactiveInteractionEngine(context, InitiativePreferences(level="normal"), clock=lambda: clock[0])
    return context, policy, clock


ARGS = dict(enabled=True, busy=False, focused=False, now=datetime(2026, 10, 22, 12))


def emit(context, key="test", **extra):
    return context.emit("own_tasks", "task_failed", key, "testes do projeto", **extra)


def test_idle_without_relevant_event_never_emits_generic_invitation(engines):
    _, engine, clock = engines
    clock[0] += 10000
    assert engine.poll(**ARGS) is None
    assert engine.history() == []


def test_contextual_invitation_deduplicates_and_survives_restart(engines):
    context, engine, clock = engines
    emit(context, ttl=86400)
    clock[0] += 300
    assert "testes do projeto" in engine.poll(**ARGS)
    assert "sensor autorizado" in engine.last_explanation
    assert emit(context, ttl=86400) is None
    clock[0] += 1800
    restarted = ProactiveInteractionEngine(context, engine.preferences, clock=lambda: clock[0])
    clock[0] += 300
    assert restarted.poll(**ARGS) is None
    assert len(restarted.history()) == 1


@pytest.mark.parametrize("override", [
    {"busy": True}, {"focused": True}, {"enabled": False},
    {"now": datetime(2026, 10, 22, 22)}, {"resource_pressure": True},
])
def test_inconvenient_interruptions_are_suppressed(engines, override):
    context, engine, clock = engines
    emit(context)
    clock[0] += 300
    assert engine.poll(**(ARGS | override)) is None
    assert not engine.history()


def test_persistent_daily_limit_and_decline_backoff(engines):
    context, engine, clock = engines
    clock[0] += 300
    emit(context, "1", ttl=86400)
    assert engine.poll(**ARGS)
    engine.respond(engine.last_offer_id, "declined")
    clock[0] += 1800
    emit(context, "2", ttl=86400)
    assert engine.poll(**ARGS) is None
    clock[0] += 1800
    assert engine.poll(**ARGS)
    clock[0] += 1800
    emit(context, "3", ttl=86400)
    assert engine.poll(**ARGS)
    clock[0] += 1800
    emit(context, "4", ttl=86400)
    assert engine.poll(**ARGS) is None


def test_resolved_expired_or_revoked_events_never_trigger(engines):
    context, engine, clock = engines
    identifier = emit(context, "resolved")
    context.resolve(identifier)
    emit(context, "expired", ttl=30)
    clock[0] += 300
    assert engine.poll(**ARGS) is None
    emit(context, "revoked")
    context.set_permission("own_tasks", False)
    assert engine.poll(**ARGS) is None


def test_concurrent_polls_offer_event_only_once(engines):
    context, engine, clock = engines
    emit(context)
    clock[0] += 300
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: engine.poll(**ARGS), range(2)))
    assert sum(result is not None for result in results) == 1


def test_disabled_sensor_does_not_invoke_collector(engines):
    context, _, _ = engines
    calls = []
    assert context.collect("processes", lambda: calls.append(True)) == []
    context.set_permission("own_tasks", False)
    assert context.collect("own_tasks", lambda: calls.append(True)) == []
    assert calls == []


def test_collection_is_debounced_and_pressure_suppressed(engines):
    context, _, clock = engines
    calls = []
    def sensor():
        calls.append(True)
        return [dict(kind="task_failed", key="one", title="build")]
    assert context.collect("own_tasks", sensor)
    assert context.collect("own_tasks", sensor) == []
    clock[0] += 6
    assert context.collect("own_tasks", sensor, under_load=True) == []
    assert len(calls) == 1


def test_event_storage_and_audit_are_bounded_and_redacted(engines):
    context, _, _ = engines
    context.MAX_EVENTS = 4
    for index in range(6):
        context.emit("own_tasks", "task_failed", str(index), "token=private password=hidden")
    with context.connect() as db:
        rows = db.execute("SELECT * FROM context_events").fetchall()
    assert len(rows) == 4
    assert all("private" not in row["title"] and "hidden" not in row["title"] for row in rows)
    assert len(context.access_history()) == 6


def test_overnight_hours_and_off_level(engines):
    context, engine, clock = engines
    emit(context)
    clock[0] += 300
    engine.preferences = InitiativePreferences(level="off")
    assert engine.poll(**ARGS) is None
    engine.preferences = InitiativePreferences(level="normal", start_hour=22, end_hour=6)
    assert engine.poll(**ARGS) is None
    assert engine.poll(**(ARGS | {"now": datetime(2026,10,22,23)}))
