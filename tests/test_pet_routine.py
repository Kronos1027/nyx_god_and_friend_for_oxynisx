"""Idle routine timing for the companion, without a window."""

import random

from ui.pet_routine import PetRoutine


class Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FixedRng:
    """uniform() returns the lower bound; random() returns the configured roll."""

    def __init__(self, roll: float = 0.9) -> None:
        self.roll = roll

    def uniform(self, low: float, high: float) -> float:
        return low

    def random(self) -> float:
        return self.roll


def test_routine_stays_quiet_until_the_first_look_window():
    clock = Clock()
    routine = PetRoutine(rng=FixedRng(), clock=clock)

    assert routine.tick().kind == "idle"
    clock.advance(PetRoutine.LOOK_INTERVAL_SECONDS[0] - 0.1)
    assert routine.tick().kind == "idle"

    clock.advance(0.2)
    action = routine.tick()
    assert action.kind == "look"
    assert action.direction is not None


def test_look_direction_points_outward():
    clock = Clock()
    routine = PetRoutine(rng=FixedRng(), clock=clock)
    clock.advance(PetRoutine.LOOK_INTERVAL_SECONDS[0])

    action = routine.tick()

    x, y = action.direction
    assert abs(x) == 40.0  # cosine of angle 0 times the minimum reach
    assert y == 0.0


def test_perk_is_chosen_when_the_roll_is_low():
    clock = Clock()
    routine = PetRoutine(rng=FixedRng(roll=0.0), clock=clock)
    clock.advance(PetRoutine.LOOK_INTERVAL_SECONDS[0])

    assert routine.tick().kind == "perk"


def test_companion_sleeps_after_the_idle_window_and_wakes_on_activity():
    clock = Clock()
    routine = PetRoutine(rng=FixedRng(), clock=clock)

    clock.advance(PetRoutine.SLEEP_AFTER_SECONDS)
    assert routine.tick().kind == "sleep"
    assert routine.sleeping is True
    assert routine.tick().kind == "sleep"

    assert routine.notify_activity() is True
    assert routine.sleeping is False
    assert routine.tick().kind == "idle"

    clock.advance(PetRoutine.LOOK_INTERVAL_SECONDS[0])
    assert routine.tick().kind == "look"


def test_activity_postpones_sleep():
    clock = Clock()
    routine = PetRoutine(rng=FixedRng(), clock=clock)

    clock.advance(PetRoutine.SLEEP_AFTER_SECONDS - 10)
    routine.notify_activity()
    clock.advance(PetRoutine.SLEEP_AFTER_SECONDS - 10)

    assert routine.tick().kind != "sleep"
    assert routine.sleeping is False


def test_directions_vary_and_stay_within_reach():
    clock = Clock()
    routine = PetRoutine(rng=random.Random(3), clock=clock)
    seen = set()

    for _ in range(8):
        clock.advance(PetRoutine.LOOK_INTERVAL_SECONDS[1] + 1)
        action = routine.tick()
        if action.kind == "look":
            x, y = action.direction
            assert 0 < (x * x + y * y) ** 0.5 <= 100
            seen.add((round(x), round(y)))
        routine.notify_activity()

    assert len(seen) > 3


def test_interacting_right_after_waking_does_not_report_sleep_again():
    clock = Clock()
    routine = PetRoutine(rng=FixedRng(), clock=clock)
    clock.advance(PetRoutine.SLEEP_AFTER_SECONDS)
    assert routine.tick().kind == "sleep"

    assert routine.notify_activity() is True
    assert routine.notify_activity() is False
