"""Bounded conversation invitations; no inference, observation or tool execution."""

from datetime import datetime
import time


class ConversationInitiative:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.last_activity = clock()
        self.last_invitation = float("-inf")
        self.invited = False
        self.day = None
        self.count = 0

    def activity(self):
        self.last_activity = self.clock()
        self.invited = False

    def poll(self, *, enabled, busy, focused, now=None):
        now = now or datetime.now()
        if self.day != now.date():
            self.day, self.count = now.date(), 0
        elapsed = self.clock()
        if (not enabled or busy or focused or not 9 <= now.hour < 21
                or self.invited or self.count >= 3
                or elapsed - self.last_activity < 300
                or elapsed - self.last_invitation < 1800):
            return None
        self.invited = True
        self.last_invitation = elapsed
        self.count += 1
        return "Oi! Quer conversar um pouco ou escolher algo para criarmos juntas? Estou por aqui."
