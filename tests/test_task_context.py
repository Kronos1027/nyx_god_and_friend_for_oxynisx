"""Stress memory-safe, deterministic planning ledgers after dozens of actions."""
import json

import pytest

from core.task_context import compact_task_ledger
from core.task_runner import TaskRunner


def steps(count):
    return [{
        "tool": "read_file" if i % 2 else "browser",
        "params": {"path": f"/fixture/file_{i}.txt", "options": "x" * 1000},
        "ok": i != 1,
        "verified": i != 1,
        "output": ("private-output:" + str(i) + ":") * 150,
        "output_truncated": True,
    } for i in range(count)]


def test_48_step_ledger_is_valid_json_and_size_bounded():
    ledger = compact_task_ledger(steps(48), max_chars=2200)
    data = json.loads(ledger)
    assert len(ledger) <= 2200
    assert data["total_steps"] == 48
    assert data["older"]["count"] == 40
    assert data["older"]["failed_or_unverified"] == 1
    assert data["older"]["earlier_failures"][0]["step"] == 2
    assert data["recent"][-1]["n"] == 48
    assert data["authority"] == "untrusted_tool_observations"
    assert "private-output:1" not in ledger  # no old raw content.


def test_evidence_preserves_last_eight_steps_in_order():
    data = json.loads(compact_task_ledger(steps(30), max_chars=4000))
    assert [s["n"] for s in data["recent"]] == list(range(23, 31))
    assert data["recent_omitted"] == 0
    assert all(len(s["params_sha12"]) == 12 for s in data["recent"])
    assert data["older"]["verified"] == 21


def test_determinism_and_limit_inputs():
    scenario = steps(32)
    assert compact_task_ledger(scenario) == compact_task_ledger(scenario)
    for bad in (100, 12001, False):
        with pytest.raises(ValueError):
            compact_task_ledger(scenario, max_chars=bad)
    with pytest.raises(ValueError):
        compact_task_ledger(scenario, recent_limit=17)


def test_1200_character_fallback_is_parseable():
    ledger = compact_task_ledger(steps(48), max_chars=1200, recent_limit=16)
    parsed = json.loads(ledger)
    assert len(ledger) <= 1200
    assert parsed["total_steps"] == 48
    assert "recent" in parsed


def test_runner_uses_compacted_ledger_after_twelve_steps():
    class Loop:
        history = []
    runner = TaskRunner(Loop())
    runner.steps = steps(48)
    context = runner._planning_history()
    raw = context[-1]["content"]
    data = json.loads(raw.split("\n", 1)[1])
    assert data["format"] == "nyx_compacted_ledger_v1"
    assert data["older"]["count"] == 40
    assert data["recent"][-1]["n"] == 48
    assert len(raw) < 4200


def test_legacy_short_ledger_keeps_each_action():
    class Loop:
        history = []
    runner = TaskRunner(Loop())
    runner.steps = steps(12)
    raw = runner._planning_history()[-1]["content"]
    data = json.loads(raw.split("\n", 1)[1])
    assert isinstance(data, list) and len(data) == 12
    assert data[1]["verified"] is False
