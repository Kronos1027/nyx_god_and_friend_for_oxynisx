"""Bounded IPC to an owned UIA process, isolated from Qt's COM state."""
import atexit
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from uuid import uuid4


class AutomationInterrupted(RuntimeError):
    def __init__(self, message, *, outcome_unknown=False):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


class WindowsAutomationClient:
    def __init__(self, control, timeout=8):
        self.control = control
        self.timeout = timeout
        self._lock = threading.Lock()
        self._process = None
        self._responses = None
        atexit.register(self.close)

    def close(self):
        process, self._process = self._process, None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()

    def _start(self):
        if self._process and self._process.poll() is None:
            return
        self.close()
        if getattr(sys, "frozen", False):
            raise RuntimeError("UIA isolada ainda não está disponível neste pacote; use a execução pelo código-fonte.")
        process = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).with_name("windows_worker.py"))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._process = process
        responses = self._responses = queue.Queue(maxsize=2)

        def read():
            try:
                while True:
                    line = process.stdout.readline(131073)
                    if not line or len(line) > 131072:
                        break
                    responses.put_nowait(json.loads(line))
            except (ValueError, OSError, queue.Full):
                pass
            finally:
                try:
                    responses.put_nowait(None)
                except queue.Full:
                    pass
        threading.Thread(target=read, daemon=True, name="nyx-uia-reader").start()

    def call(self, verb, params):
        deadline = time.monotonic() + self.timeout
        while not self._lock.acquire(timeout=0.05):
            self.control.check()
            if time.monotonic() >= deadline:
                raise AutomationInterrupted("UIA ocupada; nenhuma nova ação enviada.")
        sent = False
        mutation = verb == "focus" or (verb == "act" and params.get("action") != "read_element")
        try:
            self.control.check()
            self._start()
            token = uuid4().hex
            payload = json.dumps({"id": token, "verb": verb, "params": params}, ensure_ascii=True) + "\n"
            if len(payload) > 131072:
                raise ValueError("Pedido UIA excede o limite.")
            sent = True
            process = self._process
            responses = self._responses
            def send():
                try:
                    process.stdin.write(payload)
                    process.stdin.flush()
                except (OSError, ValueError):
                    try:
                        responses.put_nowait(None)
                    except queue.Full:
                        pass
            threading.Thread(target=send, daemon=True, name="nyx-uia-writer").start()
            while True:
                self.control.check()
                if time.monotonic() >= deadline:
                    raise TimeoutError("Prazo da operação UIA excedido.")
                try:
                    response = self._responses.get(timeout=0.05)
                except queue.Empty:
                    continue
                if response is None or response.get("id") != token:
                    raise OSError("O processo UIA encerrou sem confirmar o resultado.")
                if "error" in response:
                    if response.get("outcome_unknown"):
                        raise AutomationInterrupted(response["error"], outcome_unknown=True)
                    raise ValueError(response["error"])
                return response["data"]
        except ValueError:
            raise
        except Exception as exc:
            self.close()
            raise AutomationInterrupted(str(exc), outcome_unknown=sent and mutation) from exc
        finally:
            self._lock.release()

    def inspect(self, params):
        return self.call("inspect", params)

    def act(self, action, params):
        return self.call("act", {"action": action, "params": params})
