"""Development-only x64 loader trace for an owned, suspended LPAC child.

Enables loader snaps in that child's PEB only. No registry/global flags change.
Never attaches to an existing/user process and never relaxes the child's token.
"""

import ctypes as C
from ctypes import wintypes as W
import struct


class LoaderTrace:
    def __init__(self, api):
        if C.sizeof(C.c_void_p) != 8:
            raise RuntimeError("This diagnostic requires x64")
        self.api = api
        self.process = None
        self.lines = []
        self.original = api.CreateProcessW
        self.ntdll = C.WinDLL("ntdll")
        self.ntdll.NtQueryInformationProcess.argtypes = [
            W.HANDLE,
            W.ULONG,
            C.c_void_p,
            W.ULONG,
            C.c_void_p,
        ]
        self.kernel = api.kernel
        self.kernel.WaitForDebugEvent.argtypes = [C.c_void_p, W.DWORD]
        self.kernel.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
        api.CreateProcessW = self.create

    def create(self, *args):
        import win32process

        changed = list(args)
        changed[5] |= 2  # DEBUG_ONLY_THIS_PROCESS, keep CREATE_SUSPENDED
        result = self.original(*changed)
        if not result:
            return result
        from core.windows_sandbox import ProcessInfo

        info = C.cast(changed[-1], C.POINTER(ProcessInfo)).contents
        self.process = info.hProcess
        basic = (C.c_void_p * 6)()
        status = self.ntdll.NtQueryInformationProcess(self.process, 0, basic, C.sizeof(basic), None)
        if status != 0:
            raise RuntimeError(f"PEB query failed: {status}")
        flag_address = basic[1] + 0xBC
        previous = struct.unpack(
            "<I", win32process.ReadProcessMemory(self.process, flag_address, 4)
        )[0]
        win32process.WriteProcessMemory(self.process, flag_address, struct.pack("<I", previous | 2))
        return result

    def pump(self):
        import win32process

        event = C.create_string_buffer(176)
        # Bounded: the launcher's deadline must still get checked.
        for _ in range(64):
            if not self.kernel.WaitForDebugEvent(event, 0):
                break
            kind, pid, tid = struct.unpack_from("<III", event.raw)
            status = 0x10002
            try:
                if kind == 8:
                    address, unicode, count = struct.unpack_from("<QHH", event.raw, 16)
                    raw = win32process.ReadProcessMemory(
                        self.process, address, min(count * (2 if unicode else 1), 8192)
                    )
                    self.lines.append(
                        raw.decode("utf-16-le" if unicode else "utf-8", errors="replace").rstrip(
                            "\0"
                        )
                    )
                elif kind in (3, 6):
                    handle = struct.unpack_from("<Q", event.raw, 16)[0]
                    if handle:
                        self.api.CloseHandle(handle)
                elif kind == 1:
                    code = struct.unpack_from("<I", event.raw, 16)[0]
                    self.lines.append(f"Exception: 0x{code:08x}")
                    if code not in (0x80000003, 0x80000004):
                        status = 0x80010001
            finally:
                self.kernel.ContinueDebugEvent(pid, tid, status)
        return False
