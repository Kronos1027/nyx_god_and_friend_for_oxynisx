"""Recover model availability on later requests without restarting the app."""

from __future__ import annotations

import threading
import time
import inspect

from core.llm_client import BackendUnavailable, OfflineLLM
from core.runtime_budget import InferenceBusyError


class RecoveringLLM:
    def __init__(self, client, factory, retry_seconds=30, clock=time.monotonic):
        self._client = client
        self._factory = factory
        self._clock = clock
        self._retry_seconds = max(5, retry_seconds)
        self._next_retry = clock() + self._retry_seconds
        self._refresh_lock = threading.Lock()
        self._keep_alive = getattr(client, "keep_alive", None)

    @property
    def model(self):
        return getattr(self._client, "model", None)

    @property
    def unavailable_reason(self):
        return getattr(self._client, "unavailable_reason", "")

    @property
    def keep_alive(self):
        return self._keep_alive

    @keep_alive.setter
    def keep_alive(self, value):
        self._keep_alive = value
        if hasattr(self._client, "keep_alive"):
            self._client.keep_alive = value

    def _refresh_if_due(self):
        if not self.unavailable_reason or self._clock() < self._next_retry:
            return
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            if not self.unavailable_reason or self._clock() < self._next_retry:
                return
            self._next_retry = self._clock() + self._retry_seconds
            try:
                client = self._factory()
                if self._keep_alive is not None and hasattr(client, "keep_alive"):
                    client.keep_alive = self._keep_alive
                self._client = client
            except Exception:
                self._client = OfflineLLM(unavailable_reason="O runtime local ainda não está disponível. Vou verificar novamente em um próximo pedido.")
        finally:
            self._refresh_lock.release()

    def generate(self, user_input, history=None, memory_context=None, task_tools=None):
        self._refresh_if_due()
        client = self._client
        try:
            parameters = inspect.signature(client.generate).parameters
            kwargs = {"history": history}
            if "memory_context" in parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
                kwargs["memory_context"] = memory_context
            if "task_tools" in parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
                kwargs["task_tools"] = task_tools
            return client.generate(user_input, **kwargs)
        except BackendUnavailable as exc:
            # Queue contention is not evidence that the provider is unavailable.
            if isinstance(exc.__cause__, InferenceBusyError):
                raise
            with self._refresh_lock:
                if self._client is client:
                    self._client = OfflineLLM(unavailable_reason="O modelo local ficou indisponível. Vou reavaliar o runtime e a memória em um próximo pedido.")
                    self._next_retry = self._clock() + self._retry_seconds
            # Do not retry this generation automatically; a later request can recover.
            raise
