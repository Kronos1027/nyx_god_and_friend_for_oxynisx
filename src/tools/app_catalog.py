"""Catálogo UWP registrado e identidade de processo, sem correspondência por título."""
import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import re
import subprocess
from threading import Lock
import time

_lock = Lock()
_cached = ()
_expires = 0
_shortcuts = ()
_shortcuts_expire = 0
_ID = re.compile(r"[A-Za-z0-9_.-]{1,200}![A-Za-z0-9_.-]{1,100}\Z")


def executable_shortcuts():
    """Resolve Start Menu links in a separate COM process; never run their arguments."""
    global _shortcuts, _shortcuts_expire
    with _lock:
        if time.monotonic() < _shortcuts_expire:
            return list(_shortcuts)
        powershell = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        script = r'''[Console]::OutputEncoding=[Text.UTF8Encoding]::new()
$resolver = New-Object -ComObject WScript.Shell
$roots = @([Environment]::GetFolderPath('CommonPrograms'),[Environment]::GetFolderPath('Programs'))
@($roots | ForEach-Object { Get-ChildItem -LiteralPath $_ -Filter *.lnk -Recurse -ErrorAction SilentlyContinue } |
  Select-Object -First 2048 | ForEach-Object {
    $link = $resolver.CreateShortcut($_.FullName)
    if (-not $link.Arguments) { [pscustomobject]@{name=$_.BaseName; target=$link.TargetPath} }
  }) | ConvertTo-Json -Compress'''
        try:
            result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                                    capture_output=True, timeout=10, check=True,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if len(result.stdout) > 1_048_576:
                raise ValueError('Catálogo excede 1 MiB.')
            rows = json.loads(result.stdout.decode('utf-8-sig'))
            if isinstance(rows, dict):
                rows = [rows]
            _shortcuts = tuple((r['name'], r['target']) for r in (rows or [])
                               if isinstance(r.get('name'), str) and isinstance(r.get('target'), str))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            logging.getLogger(__name__).warning('Atalhos do Menu Iniciar indisponíveis: %s', exc)
            _shortcuts = ()
        _shortcuts_expire = time.monotonic() + 60
        return list(_shortcuts)


def packaged_apps():
    """Read registered AppsFolder identities, cached for 60 seconds."""
    global _cached, _expires
    with _lock:
        if time.monotonic() < _expires:
            return list(_cached)
        powershell = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        script = '[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress'
        try:
            result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                                    capture_output=True, timeout=10, check=True,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if len(result.stdout) > 1_048_576:
                raise ValueError('Catálogo excede 1 MiB.')
            rows = json.loads(result.stdout.decode('utf-8-sig'))
            if isinstance(rows, dict):
                rows = [rows]
            _cached = tuple((r['Name'], r['AppID']) for r in (rows or [])[:4096]
                            if isinstance(r.get('Name'), str) and len(r['Name']) <= 256
                            and isinstance(r.get('AppID'), str) and _ID.fullmatch(r['AppID']))
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            logging.getLogger(__name__).warning('Catálogo UWP indisponível: %s', exc)
            _cached = ()
        _expires = time.monotonic() + 60
        return list(_cached)


def process_app_id(pid):
    """GetApplicationUserModelId with QUERY_LIMITED_INFORMATION; no elevation."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    query = kernel.GetApplicationUserModelId
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    query.restype = wintypes.LONG
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        length = wintypes.UINT(0)
        if query(handle, ctypes.byref(length), None) != 122 or not 1 <= length.value <= 1024:
            return None
        buffer = ctypes.create_unicode_buffer(length.value)
        return buffer.value if query(handle, ctypes.byref(length), buffer) == 0 else None
    finally:
        kernel.CloseHandle(handle)


def window_is_uncloaked(hwnd):
    """WS_VISIBLE alone also includes UWP surfaces hidden by the compositor."""
    dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
    query = dwm.DwmGetWindowAttribute
    query.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    query.restype = wintypes.LONG
    cloaked = wintypes.DWORD()
    if query(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
        raise OSError('Não foi possível confirmar a visibilidade DWM da janela.')
    return cloaked.value == 0


def matching_package_windows(app_id):
    import psutil
    import pygetwindow
    import pywintypes
    import win32gui
    import win32process
    matches = []
    for window in pygetwindow.getAllWindows():
        if not window.visible or not window.title:
            continue
        try:
            if not window_is_uncloaked(window._hWnd):
                continue
            _, parent_pid = win32process.GetWindowThreadProcessId(window._hWnd)
            children = [window._hWnd]
            win32gui.EnumChildWindows(window._hWnd, lambda hwnd, _, target=children: target.append(hwnd), None)
            for hwnd in children:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                created = process.create_time()
                if process_app_id(pid) != app_id:
                    continue
                if (process.is_running() and process.create_time() == created
                        and win32process.GetWindowThreadProcessId(hwnd)[1] == pid
                        and win32process.GetWindowThreadProcessId(window._hWnd)[1] == parent_pid):
                    matches.append({'hwnd': window._hWnd, 'pid': pid, 'created': created,
                                    'owner': 'registered_app_user_model_id'})
                    break
        except (OSError, psutil.Error, pywintypes.error):
            continue
    return matches


def launch_package(app):
    # Revalidate registration before dispatch, never launch a caller-supplied ID.
    if not _ID.fullmatch(app.app_id) or (app.name, app.app_id) not in packaged_apps():
        raise ValueError('Identidade UWP não está registrada neste catálogo.')
    subprocess.Popen([str(app.path), 'shell:AppsFolder\\' + app.app_id],
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
