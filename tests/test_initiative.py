from datetime import datetime

from core.initiative import ConversationInitiative


def test_invitation_waits_and_does_not_repeat_without_interaction():
    clock = [0]
    policy = ConversationInitiative(lambda: clock[0])
    args = dict(enabled=True, busy=False, focused=False, now=datetime(2026, 10, 22, 12))
    assert policy.poll(**args) is None
    clock[0] = 300
    assert policy.poll(**args)
    clock[0] = 4000
    assert policy.poll(**args) is None
    policy.activity()
    clock[0] += 300
    assert policy.poll(**args)


def test_quiet_focus_busy_disabled_and_daily_cap():
    clock = [0]
    policy = ConversationInitiative(lambda: clock[0])
    args = dict(enabled=True, busy=False, focused=False, now=datetime(2026, 10, 22, 12))
    clock[0] = 300
    for override in ({"busy": True}, {"focused": True}, {"enabled": False},
                     {"now": datetime(2026, 10, 22, 22)}):
        assert policy.poll(**(args | override)) is None
    for _ in range(3):
        policy.activity()
        clock[0] += 1800
        assert policy.poll(**args)
    policy.activity()
    clock[0] += 1800
    assert policy.poll(**args) is None
