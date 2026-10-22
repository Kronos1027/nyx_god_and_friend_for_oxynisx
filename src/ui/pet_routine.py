"""Idle routines for the Oxynisx companion.

The sprite atlas has nine emotions and directional looks, not arbitrary poses,
so a routine is a short emotion change, a temporary look direction, or sleep.
The planner is pure — clock and RNG are injected — so the timing rules can be
tested without a window, and the overlay only applies what it returns.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RoutineAction:
    """One decision: what the companion should do right now."""

    kind: str  # "idle" | "look" | "perk" | "sleep"
    direction: tuple[float, float] | None = None


class PetRoutine:
    """Decide idle behaviour from elapsed time, with a little randomness."""

    LOOK_INTERVAL_SECONDS = (16.0, 30.0)
    SLEEP_AFTER_SECONDS = 240.0
    PERK_CHANCE = 0.18
    LOOK_HOLD_SECONDS = 2.6

    def __init__(
        self,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rng = rng or random.Random()
        self._clock = clock
        now = self._clock()
        self._last_activity = now
        self._next_look = now + self._rng.uniform(*self.LOOK_INTERVAL_SECONDS)
        self._sleeping = False

    @property
    def sleeping(self) -> bool:
        return self._sleeping

    def notify_activity(self) -> bool:
        """Reset the idle clock; returns True when the companion was asleep."""
        was_asleep = self._sleeping
        now = self._clock()
        self._last_activity = now
        self._sleeping = False
        self._next_look = now + self._rng.uniform(*self.LOOK_INTERVAL_SECONDS)
        return was_asleep

    def tick(self) -> RoutineAction:
        """Return the action for this tick; safe to call every second."""
        now = self._clock()
        if self._sleeping:
            return RoutineAction("sleep")
        if now - self._last_activity >= self.SLEEP_AFTER_SECONDS:
            self._sleeping = True
            return RoutineAction("sleep")
        if now < self._next_look:
            return RoutineAction("idle")

        self._next_look = now + self._rng.uniform(*self.LOOK_INTERVAL_SECONDS)
        if self._rng.random() < self.PERK_CHANCE:
            return RoutineAction("perk")
        angle = self._rng.uniform(0.0, 2.0 * math.pi)
        reach = self._rng.uniform(0.4, 1.0)
        return RoutineAction("look", (math.cos(angle) * reach * 100, math.sin(angle) * reach * 100))
