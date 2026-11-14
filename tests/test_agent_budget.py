"""Extended read-only teams must never turn into unbounded workers."""
import pytest

from core.agent_budget import team_timeout_seconds
from core.task_graph import normalize_tasks


def test_default_two_turn_team_keeps_150_seconds():
    tasks = [{"role": "arquivos", "task": "read", "max_steps": 2} for _ in range(4)]
    assert team_timeout_seconds(tasks) == 150


def test_one_deep_agent_has_bounded_extra_budget():
    assert team_timeout_seconds([{"max_steps": 6}]) == 270
    assert team_timeout_seconds([{"max_steps": 5}]) == 240


def test_four_deep_agents_never_exceed_ten_minutes():
    assert team_timeout_seconds([{"max_steps": 6}] * 4) == 600


def test_invalid_deadlines_fail_closed():
    for item in ({"max_steps": 0}, {"max_steps": 7},
                 {"max_steps": True}, {"max_steps": "6"}):
        with pytest.raises(ValueError):
            team_timeout_seconds([item])
    with pytest.raises(ValueError):
        team_timeout_seconds([])
    with pytest.raises(ValueError):
        team_timeout_seconds([{"max_steps": 2}] * 5)


def test_graph_budget_is_explicit_only():
    tasks = normalize_tasks([{"role": "arquivos", "task": "ler"},
                             {"role": "arquivos", "task": "analisar", "max_steps": 6}],
                            {"arquivos": object()})
    assert [item["max_steps"] for item in tasks] == [2, 6]
    assert team_timeout_seconds(tasks) == 270
