"""Windows LPAC launcher. Experimental until its real acceptance suite passes.

No ambient environment, broad handles, network capabilities, or unsandboxed fallback.
Only caller-owned staging paths may receive the new per-run package SID ACL.
"""

from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
import os
import math
from pathlib import Path
import subprocess
import time


class SandboxUnavailable(RuntimeError):
    pass


class CpuRateInfo(C.Structure):
    _fields_ = [("ControlFlags", W.DWORD), ("CpuRate", W.DWORD)]


def validate_limits(timeout, memory_mib, output_limit, cpu_percent, process_limit):
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 1 <= timeout <= 300):
        raise ValueError("Limite inválido de tempo.")
    for name, value, minimum, maximum in (
        ("memória", memory_mib, 64, 512),
        ("saída", output_limit, 1, 1024 * 1024),
        ("CPU", cpu_percent, 1, 50),
        ("processos", process_limit, 1, 4),
    ):
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"Limite inválido de {name}.")


class SecurityAttributes(C.Structure):
    _fields_ = [
        ("nLength", W.DWORD),
        ("lpSecurityDescriptor", C.c_void_p),
        ("bInheritHandle", W.BOOL),
    ]


class StartupInfo(C.Structure):
    _fields_ = [
        ("cb", W.DWORD),
        ("lpReserved", W.LPWSTR),
        ("lpDesktop", W.LPWSTR),
        ("lpTitle", W.LPWSTR),
        ("dwX", W.DWORD),
        ("dwY", W.DWORD),
        ("dwXSize", W.DWORD),
        ("dwYSize", W.DWORD),
        ("dwXCountChars", W.DWORD),
        ("dwYCountChars", W.DWORD),
        ("dwFillAttribute", W.DWORD),
        ("dwFlags", W.DWORD),
        ("wShowWindow", W.WORD),
        ("cbReserved2", W.WORD),
        ("lpReserved2", C.c_void_p),
        ("hStdInput", W.HANDLE),
        ("hStdOutput", W.HANDLE),
        ("hStdError", W.HANDLE),
    ]


class StartupInfoEx(C.Structure):
    _fields_ = [("StartupInfo", StartupInfo), ("lpAttributeList", C.c_void_p)]


class ProcessInfo(C.Structure):
    _fields_ = [
        ("hProcess", W.HANDLE),
        ("hThread", W.HANDLE),
        ("dwProcessId", W.DWORD),
        ("dwThreadId", W.DWORD),
    ]


class SecurityCapabilities(C.Structure):
    _fields_ = [
        ("AppContainerSid", C.c_void_p),
        ("Capabilities", C.c_void_p),
        ("CapabilityCount", W.DWORD),
        ("Reserved", W.DWORD),
    ]


class SidAttributes(C.Structure):
    _fields_ = [("Sid", C.c_void_p), ("Attributes", W.DWORD)]


class WindowsAPI:
    def __init__(self):
        if os.name != "nt":
            raise SandboxUnavailable("O backend LPAC exige Windows.")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.security = C.WinDLL("advapi32", use_last_error=True)
        self.userenv = C.WinDLL("userenv", use_last_error=True)
        P = C.c_void_p

        def bind(dll, name, result, arguments):
            function = getattr(dll, name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)

        bind(
            self.userenv,
            "CreateAppContainerProfile",
            C.c_long,
            [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, P, W.DWORD, C.POINTER(P)],
        )
        bind(self.userenv, "DeleteAppContainerProfile", C.c_long, [W.LPCWSTR])
        bind(
            self.userenv,
            "DeriveAppContainerSidFromAppContainerName",
            C.c_long,
            [W.LPCWSTR, C.POINTER(P)],
        )
        bind(self.userenv, "GetAppContainerFolderPath", C.c_long, [W.LPCWSTR, C.POINTER(W.LPWSTR)])
        self.ole32 = C.WinDLL("ole32")
        bind(self.ole32, "CoTaskMemFree", None, [P])
        bind(self.security, "FreeSid", P, [P])
        bind(self.security, "ConvertSidToStringSidW", W.BOOL, [P, C.POINTER(W.LPWSTR)])
        bind(self.security, "ConvertStringSidToSidW", W.BOOL, [W.LPCWSTR, C.POINTER(P)])
        bind(self.security, "OpenProcessToken", W.BOOL, [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)])
        bind(
            self.security,
            "GetTokenInformation",
            W.BOOL,
            [W.HANDLE, C.c_int, P, W.DWORD, C.POINTER(W.DWORD)],
        )
        bind(self.security, "DuplicateToken", W.BOOL, [W.HANDLE, C.c_int, C.POINTER(W.HANDLE)])
        bind(
            self.security,
            "ConvertStringSecurityDescriptorToSecurityDescriptorW",
            W.BOOL,
            [W.LPCWSTR, W.DWORD, C.POINTER(P), C.POINTER(W.DWORD)],
        )
        bind(
            self.security,
            "AccessCheck",
            W.BOOL,
            [P, W.HANDLE, W.DWORD, P, P, C.POINTER(W.DWORD), C.POINTER(W.DWORD), C.POINTER(W.BOOL)],
        )
        bind(
            self.security,
            "GetFileSecurityW",
            W.BOOL,
            [W.LPCWSTR, W.DWORD, P, W.DWORD, C.POINTER(W.DWORD)],
        )
        bind(self.kernel, "LocalFree", P, [P])
        bind(self.kernel, "CloseHandle", W.BOOL, [W.HANDLE])
        bind(
            self.kernel,
            "InitializeProcThreadAttributeList",
            W.BOOL,
            [P, W.DWORD, W.DWORD, C.POINTER(C.c_size_t)],
        )
        bind(
            self.kernel,
            "UpdateProcThreadAttribute",
            W.BOOL,
            [P, W.DWORD, C.c_size_t, P, C.c_size_t, P, P],
        )
        bind(self.kernel, "DeleteProcThreadAttributeList", None, [P])
        bind(
            self.kernel,
            "CreateProcessW",
            W.BOOL,
            [W.LPCWSTR, W.LPWSTR, P, P, W.BOOL, W.DWORD, P, W.LPCWSTR, P, P],
        )
        bind(
            self.kernel,
            "CreatePipe",
            W.BOOL,
            [C.POINTER(W.HANDLE), C.POINTER(W.HANDLE), P, W.DWORD],
        )
        bind(self.kernel, "SetHandleInformation", W.BOOL, [W.HANDLE, W.DWORD, W.DWORD])
        bind(
            self.kernel,
            "CreateFileW",
            W.HANDLE,
            [W.LPCWSTR, W.DWORD, W.DWORD, P, W.DWORD, W.DWORD, W.HANDLE],
        )
        bind(self.kernel, "PeekNamedPipe", W.BOOL, [W.HANDLE, P, W.DWORD, P, C.POINTER(W.DWORD), P])
        bind(self.kernel, "ReadFile", W.BOOL, [W.HANDLE, P, W.DWORD, C.POINTER(W.DWORD), P])
        bind(self.kernel, "ResumeThread", W.DWORD, [W.HANDLE])
        bind(self.kernel, "WaitForSingleObject", W.DWORD, [W.HANDLE, W.DWORD])
        bind(self.kernel, "GetExitCodeProcess", W.BOOL, [W.HANDLE, C.POINTER(W.DWORD)])
        bind(self.kernel, "TerminateProcess", W.BOOL, [W.HANDLE, W.UINT])
        bind(self.kernel, "GetProcessMitigationPolicy", W.BOOL, [W.HANDLE, C.c_int, P, C.c_size_t])
        bind(self.kernel, "SetInformationJobObject", W.BOOL, [W.HANDLE, C.c_int, P, W.DWORD])
        bind(self.kernel, "QueryInformationJobObject", W.BOOL, [W.HANDLE, C.c_int, P, W.DWORD, P])

    def limit_cpu(self, job, percent):
        requested = CpuRateInfo(0x1 | 0x4, percent * 100)  # ENABLE | HARD_CAP
        self.check(self.SetInformationJobObject(int(job), 15, C.byref(requested), C.sizeof(requested)),
                   "Set job CPU hard cap")
        actual = CpuRateInfo()
        self.check(self.QueryInformationJobObject(int(job), 15, C.byref(actual), C.sizeof(actual), None),
                   "Verify job CPU hard cap")
        if actual.ControlFlags != requested.ControlFlags or actual.CpuRate != requested.CpuRate:
            raise SandboxUnavailable("O Job não confirmou o limite obrigatório de CPU.")

    @staticmethod
    def check(result, operation):
        if not result:
            raise SandboxUnavailable(f"{operation}: {C.WinError(C.get_last_error())}")

    def sid_string(self, sid):
        string = W.LPWSTR()
        self.check(self.ConvertSidToStringSidW(sid, C.byref(string)), "SID")
        try:
            return string.value
        finally:
            self.LocalFree(C.cast(string, C.c_void_p))

    def profile_directory(self, name):
        sid = C.c_void_p()
        result = self.DeriveAppContainerSidFromAppContainerName(name, C.byref(sid))
        if result != 0:
            raise SandboxUnavailable("Não foi possível derivar o SID do perfil isolado.")
        path = W.LPWSTR()
        try:
            result = self.GetAppContainerFolderPath(self.sid_string(sid), C.byref(path))
            if result & 0xFFFFFFFF == 0x80070002:
                return None
            if result != 0:
                raise SandboxUnavailable(
                    f"Não foi possível localizar o diretório do perfil isolado: 0x{result & 0xffffffff:08x}"
                )
            return Path(path.value)
        finally:
            self.FreeSid(sid)
            if path:
                self.CoTaskMemFree(C.cast(path, C.c_void_p))

    def token_evidence(self, process, expected_sid, expected_capabilities=()):
        token = W.HANDLE()
        self.check(self.OpenProcessToken(process, 10, C.byref(token)), "OpenProcessToken")
        try:
            values = {}
            for label, kind in (("appcontainer", 29),):
                value, needed = W.DWORD(), W.DWORD()
                self.check(
                    self.GetTokenInformation(
                        token, kind, C.byref(value), C.sizeof(value), C.byref(needed)
                    ),
                    label,
                )
                values[label] = value.value == 1
            # TokenIsLessPrivilegedAppContainer is not queryable through
            # GetTokenInformation on this Windows build (ERROR_INVALID_PARAMETER).
            # Verify the documented LPAC access semantics, with a positive control.
            values["lpac"] = not self.access_allowed(token, "S-1-15-2-1") and self.access_allowed(
                token, expected_sid
            )
            needed = W.DWORD()
            self.GetTokenInformation(token, 31, None, 0, C.byref(needed))
            info = C.create_string_buffer(needed.value)
            self.check(
                self.GetTokenInformation(token, 31, info, len(info), C.byref(needed)), "package SID"
            )
            sid = C.c_void_p.from_buffer(info)
            values["package_matches"] = self.sid_string(sid) == expected_sid
            self.GetTokenInformation(token, 30, None, 0, C.byref(needed))
            capabilities = C.create_string_buffer(needed.value)
            self.check(
                self.GetTokenInformation(
                    token, 30, capabilities, len(capabilities), C.byref(needed)
                ),
                "capabilities",
            )
            cap_count = W.DWORD.from_buffer(capabilities).value
            actual_caps = set()
            for index in range(cap_count):
                item = SidAttributes.from_buffer(
                    capabilities, C.alignment(SidAttributes) + index * C.sizeof(SidAttributes)
                )
                actual_caps.add(self.sid_string(item.Sid))
            values["capabilities_match"] = actual_caps == set(expected_capabilities)
            mitigation = W.DWORD()
            self.check(
                self.GetProcessMitigationPolicy(
                    process, 4, C.byref(mitigation), C.sizeof(mitigation)
                ),
                "Win32k policy",
            )
            values["win32k_disabled"] = bool(mitigation.value & 1)
            if not all(values.values()):
                raise SandboxUnavailable("O processo não recebeu todas as restrições obrigatórias.")
            return values
        finally:
            self.CloseHandle(token)

    def access_allowed(self, token, sid=None, path=None):
        impersonation = W.HANDLE()
        descriptor = C.c_void_p()
        self.check(self.DuplicateToken(token, 2, C.byref(impersonation)), "Duplicate query token")
        try:
            if path is None:
                sddl = f"O:SYG:SYD:(A;;0x1;;;WD)(A;;0x1;;;{sid})"
                self.check(
                    self.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                        sddl, 1, C.byref(descriptor), None
                    ),
                    "Probe descriptor",
                )
                desired, mapping = 1, (W.DWORD * 4)(1, 1, 1, 1)
            else:
                size = W.DWORD()
                self.GetFileSecurityW(str(path), 7, None, 0, C.byref(size))
                buffer = C.create_string_buffer(size.value)
                self.check(
                    self.GetFileSecurityW(str(path), 7, buffer, len(buffer), C.byref(size)),
                    "Image security descriptor",
                )
                descriptor = C.cast(buffer, C.c_void_p)
                desired, mapping = 0x1200A9, (W.DWORD * 4)(0x120089, 0x120116, 0x1200A0, 0x1F01FF)
            privileges = C.create_string_buffer(1024)
            length, granted, allowed = W.DWORD(len(privileges)), W.DWORD(), W.BOOL()
            self.check(
                self.AccessCheck(
                    descriptor,
                    impersonation,
                    desired,
                    mapping,
                    privileges,
                    C.byref(length),
                    C.byref(granted),
                    C.byref(allowed),
                ),
                "LPAC AccessCheck",
            )
            return bool(allowed.value and granted.value & 1)
        finally:
            if descriptor and path is None:
                self.LocalFree(descriptor)
            self.CloseHandle(impersonation)


class LPACProfile:
    def __init__(self, journal):
        self.api = WindowsAPI()
        self.journal = journal
        self.name = journal.reserve()
        self.sid = C.c_void_p()
        result = self.api.CreateAppContainerProfile(
            self.name,
            "Nyx isolated execution",
            "Ephemeral local code sandbox",
            None,
            0,
            C.byref(self.sid),
        )
        if result != 0:
            if result & 0xFFFFFFFF == 0x800700B7:  # pre-existing profile is not ours
                journal.forget(self.name)
            raise SandboxUnavailable(
                f"CreateAppContainerProfile falhou: HRESULT 0x{result & 0xffffffff:08x}"
            )
        try:
            self.sid_text = self.api.sid_string(self.sid)
            directory = self.api.profile_directory(self.name)
            if directory is None:
                raise SandboxUnavailable("O perfil criado não tem diretório identificável.")
            self.journal.storage(self.name, directory)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.sid:
            try:
                delete_owned_profile(self.api, self.name, self.journal.storage(self.name))
                self.journal.forget(self.name)
            finally:
                self.api.FreeSid(self.sid)
                self.sid = None

    def grant(self, staging_root, target, *, writable=False):
        # Inspect unresolved paths first: resolve() would erase a junction and
        # could make a target appear safe after already following it.
        root, target = Path(staging_root).absolute(), Path(target).absolute()
        if not target.is_relative_to(root):
            raise ValueError("ACL fora da pasta temporária de execução.")
        for path in (root, target, *target.parents):
            if path.lstat().st_file_attributes & 0x400:
                raise ValueError("Links/reparse points não recebem permissões do sandbox.")
        for directory, directories, files in os.walk(target, followlinks=False):
            for name in (*directories, *files):
                item = Path(directory) / name
                info = item.lstat()
                if info.st_file_attributes & 0x400 or (item.is_file() and info.st_nlink > 1):
                    raise ValueError("Links/reparse points não recebem permissões do sandbox.")
        root, target = root.resolve(strict=True), target.resolve(strict=True)
        if not target.is_relative_to(root):
            raise ValueError("ACL fora da pasta temporária de execução.")
        executable = str(Path(os.environ["SystemRoot"]) / "System32" / "icacls.exe")
        rights = "M" if writable else "RX"
        commands = [
            [executable, str(target), "/grant", f"*{self.sid_text}:(OI)(CI)({rights})", "/T", "/Q"]
        ]
        if writable:
            commands.append(
                [executable, str(target), "/setintegritylevel", "(OI)(CI)L", "/T", "/Q"]
            )
        for command in commands:
            result = subprocess.run(
                command, capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode:
                raise SandboxUnavailable("Não foi possível aplicar ACL ao diretório temporário.")


@contextmanager
def profile(state_dir=None):
    from core.sandbox_journal import SandboxJournal

    if state_dir is None:
        state_dir = Path(__file__).resolve().parents[2] / "data" / "sandbox" / "profiles"
    with SandboxJournal(state_dir) as journal:
        api = WindowsAPI()
        journal.recover(lambda name: delete_owned_profile(api, name, journal.storage(name)))
        instance = LPACProfile(journal)
        try:
            yield instance
        finally:
            instance.close()


def delete_owned_profile(api, name, recorded_storage=None):
    from core.sandbox_journal import NAME

    if not NAME.fullmatch(name):
        raise ValueError("Nome fora do espaço de perfis da Nyx.")
    directory = api.profile_directory(name)
    if recorded_storage is not None:
        recorded = Path(recorded_storage)
        expected = Path(os.environ["LOCALAPPDATA"]) / "Packages" / name / "AC"
        if recorded != expected or (directory is not None and directory != recorded):
            raise SandboxUnavailable("Diretório do perfil diverge do inventário; limpeza recusada.")
        directory = recorded
    result = api.DeleteAppContainerProfile(name)
    if result != 0:
        raise SandboxUnavailable(
            f"Não foi possível limpar o perfil {name}: 0x{result & 0xffffffff:08x}"
        )
    if directory is not None and directory.parent.exists():
        raise SandboxUnavailable(
            "O Windows não removeu todo o armazenamento do perfil; limpeza pendente."
        )


def stop_job(job, exit_code, timeout=5):
    """Wait on actual process handles, not the job's early accounting counters.

    TerminateJobObject removes PIDs from the job list before their process handles
    are necessarily signaled. Prevent further spawning, capture each verified
    member, terminate the job, then wait for those handles to become signaled.
    """
    import pywintypes
    import win32api
    import win32event
    import win32job

    deadline = time.monotonic() + timeout
    handles = []
    try:
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits["BasicLimitInformation"]["ActiveProcessLimit"] = 1
        limits["BasicLimitInformation"]["LimitFlags"] |= 8
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
        for pid in win32job.QueryInformationJobObject(job, win32job.JobObjectBasicProcessIdList):
            try:
                handle = win32api.OpenProcess(0x100000 | 0x1000, False, pid)
            except (OSError, pywintypes.error) as error:
                if error.winerror == 87:
                    continue
                raise
            if win32job.IsProcessInJob(handle, job):
                handles.append(handle)
            else:
                handle.Close()
        win32job.TerminateJobObject(job, exit_code)
        for handle in handles:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if win32event.WaitForSingleObject(handle, remaining) != 0:
                raise SandboxUnavailable("Processo do sandbox não confirmou encerramento.")
    finally:
        # Includes exceptional paths; kill-on-close is also configured.
        win32job.TerminateJobObject(job, exit_code)
        for handle in handles:
            handle.Close()


def run_lpac(
    container,
    executable,
    arguments,
    cwd,
    *,
    timeout=20,
    memory_mib=256,
    cancelled=lambda: False,
    output_limit=65536,
    cpu_percent=25,
    process_limit=4,
    diagnostic_registry_read=False,
    channel=None,
):
    """Launch suspended, verify token/job, then resume. No fallback is allowed."""
    validate_limits(timeout, memory_mib, output_limit, cpu_percent, process_limit)
    import win32job

    api = container.api
    process = ProcessInfo()
    handles = []
    attributes = None
    attributes_initialized = False
    capability_sid = C.c_void_p()
    job = win32job.CreateJobObject(None, container.name + ".Job")
    data = bytearray()
    stderr_data = bytearray()
    started = time.monotonic()
    state = "exited"
    input_pipe = None
    channel_claimed = False
    try:
        if channel is not None:
            from core.sandbox_channel import OverlappedInput, SandboxChannel
            if type(channel) is not SandboxChannel:
                raise ValueError("Canal de sandbox inválido.")
            channel.claim()
            channel_claimed = True
            input_pipe = OverlappedInput()
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits["BasicLimitInformation"]["LimitFlags"] = 0x2000 | 0x200 | 0x100 | 0x8 | 0x4
        limits["BasicLimitInformation"]["ActiveProcessLimit"] = process_limit
        limits["BasicLimitInformation"]["PerJobUserTimeLimit"] = int(timeout * 10_000_000)
        limits["ProcessMemoryLimit"] = limits["JobMemoryLimit"] = memory_mib * 1048576
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
        api.limit_cpu(job, cpu_percent)
        win32job.SetInformationJobObject(
            job, win32job.JobObjectBasicUIRestrictions, {"UIRestrictionsClass": 0xFF}
        )
        sa = SecurityAttributes(C.sizeof(SecurityAttributes), None, True)
        read, write = W.HANDLE(), W.HANDLE()
        api.check(api.CreatePipe(C.byref(read), C.byref(write), C.byref(sa), 0), "CreatePipe")
        handles.extend([read.value, write.value])
        api.check(api.SetHandleInformation(read, 1, 0), "Protect read handle")
        stderr_read = stderr_write = None
        if channel is not None:
            stderr_read, stderr_write = W.HANDLE(), W.HANDLE()
            api.check(api.CreatePipe(C.byref(stderr_read), C.byref(stderr_write), C.byref(sa), 0), "Create stderr pipe")
            handles.extend([stderr_read.value, stderr_write.value])
            api.check(api.SetHandleInformation(stderr_read, 1, 0), "Protect stderr read handle")
        if input_pipe is not None:
            nul = int(input_pipe.reader)
        else:
            nul = api.CreateFileW("NUL", 0x80000000, 3, C.byref(sa), 3, 0, None)
            if nul == C.c_void_p(-1).value:
                raise SandboxUnavailable("Não foi possível criar stdin vazio.")
            handles.append(nul)
        count = C.c_size_t()
        api.InitializeProcThreadAttributeList(None, 5, 0, C.byref(count))
        attributes = C.create_string_buffer(count.value)
        api.check(
            api.InitializeProcThreadAttributeList(attributes, 5, 0, C.byref(count)),
            "Initialize attributes",
        )
        attributes_initialized = True
        capabilities = SecurityCapabilities(container.sid, None, 0, 0)
        expected_caps = []
        if diagnostic_registry_read:
            # Microsoft's named registryRead capability. Diagnostic only; does
            # not grant network capabilities or change filesystem ACLs.
            expected_caps = [
                "S-1-15-3-1024-1065365936-1281604716-3511738428-1654721687-432734479-3232135806-4053264122-3456934681"
            ]
            api.check(
                api.ConvertStringSidToSidW(expected_caps[0], C.byref(capability_sid)),
                "Registry capability SID",
            )
            cap_array = (SidAttributes * 1)(SidAttributes(capability_sid, 4))
            capabilities.Capabilities = C.cast(cap_array, C.c_void_p)
            capabilities.CapabilityCount = 1
        lpac = W.DWORD(1)
        mitigation = C.c_ulonglong(1 << 28)  # disable Win32k system calls
        inherited_values = [write.value, nul]
        if stderr_write is not None:
            inherited_values.append(stderr_write.value)
        inherited = (W.HANDLE * len(inherited_values))(*inherited_values)
        assigned_jobs = (W.HANDLE * 1)(int(job))
        for attribute, value in (
            (0x20009, capabilities),
            (0x2000F, lpac),
            (0x20007, mitigation),
            (0x20002, inherited),
            (0x2000D, assigned_jobs),  # atomic job assignment during process creation
        ):
            api.check(
                api.UpdateProcThreadAttribute(
                    attributes, 0, attribute, C.byref(value), C.sizeof(value), None, None
                ),
                "Update attributes",
            )
        startup = StartupInfoEx()
        startup.StartupInfo.cb = C.sizeof(startup)
        startup.StartupInfo.dwFlags = 0x100  # explicit stdio handles only
        startup.StartupInfo.hStdInput = nul
        startup.StartupInfo.hStdOutput = startup.StartupInfo.hStdError = write.value
        if stderr_write is not None:
            startup.StartupInfo.hStdError = stderr_write.value
        startup.lpAttributeList = C.cast(attributes, C.c_void_p)
        environment = {
            "SystemRoot": os.environ["SystemRoot"],
            "WINDIR": os.environ["SystemRoot"],
            "LOCALAPPDATA": os.environ["LOCALAPPDATA"],
            "TEMP": str(cwd),
            "TMP": str(cwd),
            "USERPROFILE": str(cwd),
            "PATH": str(Path(executable).parent),
        }
        block = C.create_unicode_buffer(
            "\0".join(f"{k}={v}" for k, v in sorted(environment.items())) + "\0\0"
        )
        command = C.create_unicode_buffer(subprocess.list2cmdline([str(executable), *arguments]))
        flags = 0x80000 | 0x400 | 0x08000000 | 4
        api.check(
            api.CreateProcessW(
                str(executable),
                command,
                None,
                None,
                True,
                flags,
                block,
                str(cwd),
                C.byref(startup),
                C.byref(process),
            ),
            "Create LPAC process",
        )
        api.CloseHandle(write.value)
        handles.remove(write.value)
        if stderr_write is not None:
            api.CloseHandle(stderr_write.value)
            handles.remove(stderr_write.value)
        if input_pipe is not None:
            input_pipe.release_parent_reader()
        if not win32job.IsProcessInJob(int(process.hProcess), job):
            raise SandboxUnavailable("O processo não nasceu no Job obrigatório.")
        evidence = api.token_evidence(process.hProcess, container.sid_text, expected_caps)
        token = W.HANDLE()
        api.check(api.OpenProcessToken(process.hProcess, 10, C.byref(token)), "Image token")
        try:
            evidence["image_acl_read_execute"] = api.access_allowed(token, path=executable)
            evidence["python_dll_acl_read_execute"] = api.access_allowed(
                token, path=Path(executable).with_name("python311.dll")
            )
            evidence["system_kernel_acl_read_execute"] = api.access_allowed(
                token, path=Path(os.environ["SystemRoot"]) / "System32" / "kernel32.dll"
            )
            for name in (
                "ntdll.dll",
                "kernelbase.dll",
                "ucrtbase.dll",
                "advapi32.dll",
                "bcrypt.dll",
                "version.dll",
                "ws2_32.dll",
                "sechost.dll",
            ):
                evidence[name] = api.access_allowed(
                    token, path=Path(os.environ["SystemRoot"]) / "System32" / name
                )
            evidence["vcruntime140.dll"] = api.access_allowed(
                token, path=Path(executable).with_name("vcruntime140.dll")
            )
            evidence["workspace_rx"] = api.access_allowed(token, path=cwd)
        finally:
            api.CloseHandle(token)
        if cancelled() or (channel is not None and channel.stop_requested.is_set()):
            state = "cancelled"
        else:
            if api.ResumeThread(process.hThread) == 0xFFFFFFFF:
                raise SandboxUnavailable("Não foi possível iniciar a thread isolada.")
            if channel is not None:
                channel.started.set()
            while True:
                if cancelled() or (channel is not None and channel.stop_requested.is_set()):
                    state = "cancelled"
                    break
                if time.monotonic() - started >= timeout:
                    state = "timed_out"
                    break
                if input_pipe is not None:
                    input_pipe.pump(channel)
                read_any = False
                for pipe, target in ((read, data), (stderr_read, stderr_data)):
                    if pipe is None:
                        continue
                    available = W.DWORD()
                    if api.PeekNamedPipe(pipe, None, 0, None, C.byref(available), None) and available.value:
                        buffer = C.create_string_buffer(min(available.value, 16384))
                        received = W.DWORD()
                        api.check(api.ReadFile(pipe, buffer, len(buffer), C.byref(received), None), "Read sandbox output")
                        target.extend(buffer.raw[:received.value])
                        read_any = True
                        if len(data) + len(stderr_data) > output_limit:
                            state = "output_limit"
                            break
                        if channel is not None and target is data and not channel.deliver(buffer.raw[:received.value]):
                            state = "channel_backpressure"
                            break
                if state in ("output_limit", "channel_backpressure"):
                    break
                if read_any:
                    continue
                if api.WaitForSingleObject(process.hProcess, 25) == 0:
                    break
        stop_job(job, 124)
        api.WaitForSingleObject(process.hProcess, 5000)
        # A short-lived child can exit during WaitForSingleObject, after the
        # preceding PeekNamedPipe. Drain the remaining output after termination.
        for pipe, target in ((read, data), (stderr_read, stderr_data)):
            if pipe is None:
                continue
            while len(data) + len(stderr_data) <= output_limit:
                available = W.DWORD()
                if not api.PeekNamedPipe(pipe, None, 0, None, C.byref(available), None) or not available.value:
                    break
                buffer = C.create_string_buffer(min(available.value, 16384))
                received = W.DWORD()
                api.check(api.ReadFile(pipe, buffer, len(buffer), C.byref(received), None), "Drain sandbox output")
                target.extend(buffer.raw[:received.value])
                if channel is not None and target is data and len(data) + len(stderr_data) <= output_limit:
                    if not channel.deliver(buffer.raw[:received.value]):
                        state = "channel_backpressure"
                        break
        if len(data) + len(stderr_data) > output_limit and state == "exited":
            state = "output_limit"
        code = W.DWORD()
        api.check(api.GetExitCodeProcess(process.hProcess, C.byref(code)), "Exit code")
        usage = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        accounting = win32job.QueryInformationJobObject(job, win32job.JobObjectBasicAccountingInformation)
        return {
            "state": state,
            "returncode": code.value,
            "output": data[:output_limit].decode("utf-8", errors="replace"),
            "stderr": stderr_data[:max(0, output_limit - len(data))].decode("utf-8", errors="replace"),
            "seconds": round(time.monotonic() - started, 3),
            "peak_job_memory": usage["PeakJobMemoryUsed"],
            "job_user_seconds": accounting["TotalUserTime"] / 10_000_000,
            "job_kernel_seconds": accounting["TotalKernelTime"] / 10_000_000,
            "limits": {"timeout": timeout, "memory_mib": memory_mib, "output_bytes": output_limit,
                       "cpu_percent": cpu_percent, "processes": process_limit},
            "isolation": evidence,
            "pid": process.dwProcessId,
        }
    finally:
        try:
            stop_job(job, 125)
        finally:
            if process.hProcess:
                api.TerminateProcess(
                    process.hProcess, 125
                )  # also covers failure before job assignment
                api.WaitForSingleObject(process.hProcess, 5000)
            job.Close()
            for handle in (process.hProcess, process.hThread, *handles):
                if handle:
                    api.CloseHandle(handle)
            if attributes_initialized:
                api.DeleteProcThreadAttributeList(attributes)
            if capability_sid:
                api.LocalFree(capability_sid)
            try:
                if input_pipe is not None:
                    input_pipe.close()
            finally:
                if channel_claimed:
                    channel.finish()
