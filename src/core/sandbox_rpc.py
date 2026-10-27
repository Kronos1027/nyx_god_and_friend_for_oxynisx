"""Bounded JSON-RPC exchange over an already supervised LPAC channel.

This adapter does not launch commands, approve tools, or expose host services.
"""

import json
import math
import queue
import threading
import time

from core.sandbox_channel import SandboxChannel


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Chave JSON duplicada.")
        value[key] = item
    return value


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Número JSON não finito.")
    return value


def _invalid_constant(_text):
    raise ValueError("Constante JSON inválida.")


class SandboxRPC:
    def __init__(self, channel, *, timeout=5, cancelled=lambda: False):
        if type(channel) is not SandboxChannel:
            raise TypeError("RPC requer SandboxChannel.")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0.05 <= timeout <= 30:
            raise ValueError("Timeout RPC deve estar entre 0,05 e 30 segundos.")
        self.channel = channel
        self.timeout = timeout
        self.cancelled = cancelled
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._id = 0
        self._closed = False

    def close(self):
        self._closed = True
        self.channel.cancel()

    def _check(self, deadline):
        if self._closed or self.channel.stop_requested.is_set() or self.cancelled():
            raise RuntimeError("RPC cancelado.")
        if time.monotonic() >= deadline:
            raise TimeoutError("Prazo RPC excedido.")

    def _send(self, value):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(data) > 16384:
            raise ValueError("Mensagem RPC excede 16 KiB.")
        self.channel.send(data)

    def notify(self, method, params=None):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("RPC ocupado.")
        try:
            self._check(time.monotonic() + self.timeout)
            self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})
        finally:
            self._lock.release()

    def _read(self, deadline):
        while True:
            self._check(deadline)
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                if newline > 65536:
                    raise ValueError("Linha RPC excede limite.")
                line = bytes(self._buffer[:newline])
                del self._buffer[:newline + 1]
                message = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object,
                                     parse_constant=_invalid_constant, parse_float=_finite_float)
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise ValueError("Resposta JSON-RPC inválida.")
                return message
            if len(self._buffer) > 65536:
                raise ValueError("Linha RPC excede limite.")
            try:
                self._buffer.extend(self.channel.receive(min(0.05, max(0, deadline - time.monotonic()))))
            except queue.Empty:
                if self.channel.closed.is_set():
                    raise RuntimeError("Canal RPC encerrado.") from None

    def request(self, method, params):
        if not self._lock.acquire(blocking=False):
            return {"error": "RPC ocupado.", "_transport": {"outcome_unknown": False}}
        sent = False
        identity = None
        deadline = time.monotonic() + self.timeout
        try:
            while not self.channel.started.is_set():
                self._check(deadline)
                if self.channel.closed.is_set():
                    raise RuntimeError("Sandbox não iniciou.")
                self.channel.started.wait(0.01)
            self._check(deadline)
            self._id += 1
            identity = self._id
            self._send({"jsonrpc": "2.0", "id": identity, "method": method, "params": params})
            sent = True
            for _ in range(33):
                message = self._read(deadline)
                if "method" in message:
                    if not isinstance(message["method"], str) or "result" in message or "error" in message:
                        raise ValueError("Mensagem RPC inválida.")
                    if "id" in message:
                        if type(message["id"]) not in (str, int):
                            raise ValueError("ID de requisição inválido.")
                        # No sampling, roots, credentials or host tools are exposed.
                        response = {"result": {}} if message["method"] == "ping" else {
                            "error": {"code": -32601, "message": "Client capability unavailable"}}
                        self._send({"jsonrpc": "2.0", "id": message["id"], **response})
                    continue
                if type(message.get("id")) is not int or message["id"] != identity:
                    raise ValueError("ID de resposta RPC não corresponde à requisição.")
                if ("result" in message) == ("error" in message):
                    raise ValueError("Resposta RPC requer result ou error.")
                # Do not let untrusted top-level fields impersonate metadata
                # produced locally (for example _transport.outcome_unknown).
                key = "result" if "result" in message else "error"
                return {"jsonrpc": "2.0", "id": identity, key: message[key]}
            raise ValueError("Excesso de mensagens RPC sem resposta.")
        except (ValueError, TypeError, RuntimeError, TimeoutError, queue.Full, UnicodeError, RecursionError) as error:
            if sent:
                try:
                    self._send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                "params": {"requestId": identity, "reason": "Client stopped waiting"}})
                except (ValueError, RuntimeError, queue.Full):
                    pass
            self.close()
            return {"error": str(error), "_transport": {"outcome_unknown": sent,
                    "reason": "timeout" if isinstance(error, TimeoutError) else "rpc_stopped"}}
        finally:
            self._lock.release()
