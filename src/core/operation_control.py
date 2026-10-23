"""Cooperative interruption shared by a registry and its concrete tools."""

import threading
from contextlib import contextmanager
from contextvars import ContextVar

_local_cancel = ContextVar("nyx_operation_cancel", default=None)


@contextmanager
def operation_scope(cancelled):
    """Attach a job-local cancellation latch without cancelling unrelated jobs."""
    previous = _local_cancel.get()
    token = _local_cancel.set(lambda: cancelled() or bool(previous and previous()))
    try:
        yield
    finally:
        _local_cancel.reset(token)


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
        local = _local_cancel.get()
        return self._cancelled.is_set() or bool(local and local())

    def cancellation_probe(self):
        """Capture inherited cancellation for a worker created in another thread."""
        local = _local_cancel.get()
        return lambda: self._cancelled.is_set() or bool(local and local())

    def check(self):
        if self.is_cancelled():
            raise OperationCancelled("Operação interrompida antes da próxima ação.")
