"""Cooperative interruption shared by a registry and its concrete tools."""

import threading


class OperationCancelled(RuntimeError):
    pass


class OperationControl:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._emergency = False

    def stop(self, *, emergency=False):
        with self._lock:
            self._emergency = self._emergency or emergency
            self._cancelled.set()

    def begin(self):
        with self._lock:
            if self._emergency:
                raise OperationCancelled("Interrupção de emergência ativa. Retome as ferramentas pela interface.")
            self._cancelled.clear()

    def resume(self):
        """Only a direct UI action may call this; it is never exposed as a tool."""
        with self._lock:
            self._emergency = False
            self._cancelled.clear()

    def is_cancelled(self):
        return self._cancelled.is_set()

    def check(self):
        if self.is_cancelled():
            raise OperationCancelled("Operação interrompida antes da próxima ação.")
