"""Bounded host queues and cancellable Windows stdin for the LPAC supervisor."""

import queue
import threading
from uuid import uuid4


class SandboxChannel:
    """One-use channel. Sending never blocks the caller or grants capabilities."""

    def __init__(self):
        self._input = queue.Queue(maxsize=32)
        self._output = queue.Queue(maxsize=32)
        self._lock = threading.Lock()
        self._sent = 0
        self._claimed = False
        self.closed = threading.Event()
        self.started = threading.Event()
        self.stop_requested = threading.Event()

    def cancel(self):
        self.stop_requested.set()

    def claim(self):
        with self._lock:
            if self._claimed or self.closed.is_set():
                raise ValueError("Canal de sandbox já utilizado.")
            self._claimed = True

    def send(self, data):
        if not isinstance(data, bytes) or not 1 <= len(data) <= 16384:
            raise ValueError("Envie bytes entre 1 e 16384 por mensagem.")
        with self._lock:
            if self.closed.is_set():
                raise RuntimeError("Canal de sandbox encerrado.")
            if self._sent + len(data) > 1048576:
                raise ValueError("Orçamento total de entrada excedido.")
            self._input.put_nowait(data)
            self._sent += len(data)

    def receive(self, timeout=0.1):
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 5:
            raise ValueError("Espera inválida.")
        return self._output.get(timeout=timeout)

    def take_input(self):
        try:
            return self._input.get_nowait()
        except queue.Empty:
            return None

    def deliver(self, data):
        try:
            self._output.put_nowait(data)
            return True
        except queue.Full:
            return False

    def finish(self):
        with self._lock:
            self.closed.set()


class OverlappedInput:
    """Create handles on the host; inherit only the read endpoint into LPAC.

    All methods belong to the supervisor thread, including CancelIo. A pending
    write retains both its OVERLAPPED structure and buffer until completion.
    """

    def __init__(self):
        import pywintypes
        import win32api
        import win32event
        import win32file
        import win32pipe
        import win32security

        self.writer = self.reader = self.event = None
        self.pending = None
        self.owner = threading.get_ident()
        try:
            token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), 8)
            try:
                sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, 1)[0])
            finally:
                token.Close()
            security = pywintypes.SECURITY_ATTRIBUTES()
            security.SECURITY_DESCRIPTOR = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
                f"D:P(A;;GA;;;SY)(A;;GA;;;{sid})", 1)
            name = rf"\\.\pipe\Nyx.LPAC.Stdin.{uuid4().hex}"
            self.writer = win32pipe.CreateNamedPipe(
                name, 2 | 0x40000000 | 0x80000, 8, 1, 4096, 4096, 0, security)
            self.reader = win32file.CreateFile(name, 0x80000000, 0, None, 3, 0, None)
            # Client is already connected; ConnectNamedPipe reports 535.
            overlap = pywintypes.OVERLAPPED()
            try:
                win32pipe.ConnectNamedPipe(self.writer, overlap)
            except pywintypes.error as error:
                if error.winerror != 535:
                    raise
            win32api.SetHandleInformation(self.reader, 1, 1)
            self.event = win32event.CreateEvent(None, True, False, None)
        except Exception:
            self.close()
            raise

    def _check_thread(self):
        if self.owner != threading.get_ident():
            raise RuntimeError("I/O do sandbox fora da thread supervisora.")

    def release_parent_reader(self):
        self._check_thread()
        if self.reader is not None:
            self.reader.Close()
            self.reader = None

    def pump(self, channel):
        import pywintypes
        import win32event
        import win32file

        self._check_thread()
        if self.pending is not None:
            overlap, data = self.pending
            if win32event.WaitForSingleObject(self.event, 0) != 0:
                return
            try:
                written = win32file.GetOverlappedResult(self.writer, overlap, False)
            except Exception:
                self.pending = None  # Event signaled: completion (including errors) is final.
                raise
            if written != len(data):
                raise OSError("Escrita parcial no stdin do sandbox.")
            self.pending = None
        data = channel.take_input()
        if data is None:
            return
        win32event.ResetEvent(self.event)
        overlap = pywintypes.OVERLAPPED()
        overlap.hEvent = self.event
        self.pending = (overlap, data)
        try:
            status, _ = win32file.WriteFile(self.writer, data, overlap)
        except Exception:
            self.pending = None  # Synchronous failure did not queue this OVERLAPPED.
            raise
        if status not in (0, 997):
            self.pending = None
            raise OSError(f"Falha na entrada do sandbox: {status}")

    def close(self):
        import pywintypes
        import win32file

        self._check_thread()
        self.release_parent_reader()
        try:
            if self.pending is not None and self.writer is not None:
                win32file.CancelIo(self.writer)
                try:
                    win32file.GetOverlappedResult(self.writer, self.pending[0], True)
                except pywintypes.error as error:
                    if error.winerror not in (109, 995):
                        raise
                self.pending = None
        finally:
            for handle in (self.writer, self.event):
                if handle is not None:
                    handle.Close()
            self.writer = self.event = None
