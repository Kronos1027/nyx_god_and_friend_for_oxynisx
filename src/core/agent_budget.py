"""Deadline budget for bounded read-only specialist investigations.

Default two-turn teams retain their historical 150-second cap. Extended
investigations pay for additional turns only when explicitly requested.
The interactive task runner and user kill-switch may stop work earlier.
"""
from __future__ import annotations

DEFAULT_TEAM_SECONDS = 150
MAX_TEAM_SECONDS = 600
EXTRA_TURN_SECONDS = 30


def team_timeout_seconds(tasks: list[dict]) -> int:
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("A equipe precisa ter pelo menos uma subtarefa")
    if len(tasks) > 4:
        raise ValueError("Limite de quatro subtarefas")
    extra = 0
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("Subtarefa inválida")
        steps = task.get("max_steps", 2)
        if type(steps) is not int or not 2 <= steps <= 6:
            raise ValueError("max_steps inválido")
        extra += steps - 2
    return min(MAX_TEAM_SECONDS, DEFAULT_TEAM_SECONDS + EXTRA_TURN_SECONDS * extra)
