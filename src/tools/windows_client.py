"""Bounded IPC to an owned UIA process, isolated from Qt's COM state."""
import atexit
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from uuid import uuid4
import psutil


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
        self._worker_pid = None
        self._owned_pids = {}
        atexit.register(self.close)

    def _allow_worker_foreground(self):
        """Delegate only to this owned helper, if Windows allows the caller."""
        process = self._process
        if sys.platform != 'win32' or process is None or process.poll() is not None or self._worker_pid is None:
            return False
        try:
            worker = psutil.Process(self._worker_pid)
            if worker.create_time() != self._owned_pids.get(worker.pid) or not worker.is_running():
                return False
        except psutil.Error:
            return False
        user = ctypes.WinDLL('user32', use_last_error=True)
        allow = user.AllowSetForegroundWindow
        allow.argtypes = [wintypes.DWORD]
        allow.restype = wintypes.BOOL
        # Never ASFW_ANY, elevation, input attachment, or a system setting.
        return bool(allow(worker.pid))

    def close(self):
        process, self._process = self._process, None
        owned, self._owned_pids = self._owned_pids, {}
        self._worker_pid = None
        if process is None:
            return
        # Windows venv launchers may hide the actual interpreter two levels down.
        # Keep exact creation times, including after an intermediate exits.
        if process.poll() is None:
            try:
                for member in psutil.Process(process.pid).children(recursive=True):
                    owned[member.pid] = member.create_time()
            except psutil.Error:
                pass
        children = []
        for pid, created in owned.items():
            if pid == process.pid:
                continue
            try:
                member = psutil.Process(pid)
                if member.create_time() == created:
                    children.append(member)
                    member.terminate()
            except psutil.Error:
                pass
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
        _, alive = psutil.wait_procs(children, timeout=.2)
        for member in alive:
            try:
                if member.create_time() == owned.get(member.pid):
                    member.kill()
            except psutil.Error:
                pass
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
        try:
            ready = responses.get(timeout=min(3, self.timeout))
        except queue.Empty as exc:
            raise AutomationInterrupted('O auxiliar UIA não confirmou sua identidade no prazo.') from exc
        if not isinstance(ready, dict) or ready.get('ready') is not True or type(ready.get('pid')) is not int:
            raise AutomationInterrupted('O auxiliar UIA não confirmou uma identidade válida.')
        worker = psutil.Process(ready['pid'])
        chain = [worker, *worker.parents()]
        if process.pid not in {member.pid for member in chain}:
            raise AutomationInterrupted('O PID informado não pertence ao auxiliar iniciado pela Nyx.')
        for member in chain:
            self._owned_pids[member.pid] = member.create_time()
            if member.pid == process.pid:
                break
        self._worker_pid = worker.pid

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
            if mutation:
                self._allow_worker_foreground()
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
