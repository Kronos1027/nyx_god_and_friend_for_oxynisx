"""Native file opens that reject reparses throughout the path, atomically.

Directory enumeration uses the opened handle, never reopens its pathname.
Only local drive paths are accepted. Candidate code is never executed here.
"""

import ctypes as C
from ctypes import wintypes as W
from functools import lru_cache
import os
from pathlib import Path
import re
import struct


class ReparseRejected(OSError):
    pass


class UnicodeString(C.Structure):
    _fields_ = [("Length", W.USHORT), ("MaximumLength", W.USHORT), ("Buffer", W.LPWSTR)]


class ObjectAttributes(C.Structure):
    _fields_ = [
        ("Length", W.ULONG),
        ("RootDirectory", W.HANDLE),
        ("ObjectName", C.POINTER(UnicodeString)),
        ("Attributes", W.ULONG),
        ("SecurityDescriptor", C.c_void_p),
        ("SecurityQualityOfService", C.c_void_p),
    ]


class IOStatus(C.Structure):
    _fields_ = [("StatusOrPointer", C.c_void_p), ("Information", C.c_size_t)]


class WindowsFiles:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Native path protection requires Windows")
        self.nt = C.WinDLL("ntdll")
        self.nt.NtCreateFile.argtypes = [
            C.POINTER(W.HANDLE),
            W.ULONG,
            C.POINTER(ObjectAttributes),
            C.POINTER(IOStatus),
            C.c_void_p,
            W.ULONG,
            W.ULONG,
            W.ULONG,
            W.ULONG,
            C.c_void_p,
            W.ULONG,
        ]
        self.nt.NtCreateFile.restype = C.c_long
        self.nt.RtlNtStatusToDosError.argtypes = [C.c_long]
        self.nt.RtlNtStatusToDosError.restype = W.ULONG
        self.nt.NtQueryDirectoryFile.argtypes = [
            W.HANDLE,
            W.HANDLE,
            C.c_void_p,
            C.c_void_p,
            C.POINTER(IOStatus),
            C.c_void_p,
            W.ULONG,
            W.ULONG,
            C.c_ubyte,
            C.c_void_p,
            C.c_ubyte,
        ]
        self.nt.NtQueryDirectoryFile.restype = C.c_long

    def check(self, status):
        if status & 0xFFFFFFFF == 0xC000050B:  # STATUS_REPARSE_POINT_ENCOUNTERED
            raise ReparseRejected("O caminho contém um redirecionamento recusado pelo Windows.")
        if status < 0:
            raise C.WinError(self.nt.RtlNtStatusToDosError(status))

    def open(self, path, *, directory=False, create=False):
        import pywintypes
        import win32file

        path = Path(path).absolute()
        if not re.fullmatch(r"[A-Za-z]:", path.drive):
            raise OSError("UNC/device paths are forbidden")
        if win32file.GetDriveType(path.anchor) not in (2, 3, 6):
            raise OSError("Remote or unavailable drives are forbidden")
        text = "\\??\\" + str(path)
        encoded_length = len(text.encode("utf-16-le"))
        if encoded_length > 65530:
            raise OSError("Path exceeds UNICODE_STRING limit")
        buffer = C.create_unicode_buffer(text)
        name = UnicodeString(encoded_length, encoded_length + 2, C.cast(buffer, W.LPWSTR))
        attributes = ObjectAttributes(
            C.sizeof(ObjectAttributes), None, C.pointer(name), 0x40 | 0x1000, None, None
        )  # CASE_INSENSITIVE | DONT_REPARSE
        status_block, handle = IOStatus(), W.HANDLE()
        access = 0x100081 if directory else (0x120196 if create else 0x120089)
        options = 0x20 | (1 if directory else 0x40)  # synchronous; directory/regular file
        status = self.nt.NtCreateFile(
            C.byref(handle),
            access,
            C.byref(attributes),
            C.byref(status_block),
            None,
            0x80,
            1,
            2 if create else 1,
            options,
            None,
            0,
        )
        self.check(status)
        return pywintypes.HANDLE(handle.value)

    def entries(self, handle):
        """FILE_DIRECTORY_INFORMATION contains names/attributes from this handle."""
        restart = True
        while True:
            buffer = C.create_string_buffer(65536)
            status_block = IOStatus()
            status = self.nt.NtQueryDirectoryFile(
                int(handle),
                None,
                None,
                None,
                C.byref(status_block),
                buffer,
                len(buffer),
                1,
                False,
                None,
                restart,
            )
            if status & 0xFFFFFFFF == 0x80000006:  # STATUS_NO_MORE_FILES
                return
            self.check(status)
            restart = False
            used, offset = status_block.Information, 0
            if not 64 <= used <= len(buffer):
                raise OSError("Invalid native directory response")
            while True:
                next_offset = struct.unpack_from("<I", buffer, offset)[0]
                attributes, length = struct.unpack_from("<II", buffer, offset + 56)
                if length % 2 or offset + 64 + length > used:
                    raise OSError("Invalid native directory filename")
                name = buffer.raw[offset + 64 : offset + 64 + length].decode("utf-16-le")
                if name not in {".", ".."}:
                    yield name, attributes
                if next_offset == 0:
                    break
                if next_offset < 64 + length or offset + next_offset + 64 > used:
                    raise OSError("Invalid native directory offset")
                offset += next_offset


@lru_cache(maxsize=1)
def windows_files():
    return WindowsFiles()
