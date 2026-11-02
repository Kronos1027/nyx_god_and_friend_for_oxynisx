"""GSMTC via the Windows PowerShell 5 WinRT bridge; no optional Python package."""
from __future__ import annotations

import json
from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
from threading import RLock
import time

from core.context_awareness import safe_excerpt

# Static, read-only program. No user/page text is ever interpolated into shell code.
_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$managerType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
$propertyType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-WinRT($operation, $resultType) {
    $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
    if (-not $task.Wait(1800)) { throw 'WinRT timeout' }
    $task.Result
}
$manager = Await-WinRT ($managerType::RequestAsync()) $managerType
$session = $manager.GetCurrentSession()
if ($null -eq $session) {
    @{status='empty'; title=''; artist=''; state='none'} | ConvertTo-Json -Compress
} else {
    $info = $session.GetPlaybackInfo()
    $source = [string]$session.SourceAppUserModelId
    if ($source -notmatch '(?i)spotify|vlc|wmplayer|zunemusic|music.ui|mediaplayer|foobar2000|winamp|deezer|itunes|powershell' -or
        $source -match '(?i)chrome|msedge|firefox|brave|opera|vivaldi|keepass|bitwarden|1password|lastpass|dashlane') {
        @{status='protected'; title=''; artist=''; state=[string]$info.PlaybackStatus} | ConvertTo-Json -Compress
    } else {
        $properties = Await-WinRT ($session.TryGetMediaPropertiesAsync()) $propertyType
        $title = [string]$properties.Title
        $artist = [string]$properties.Artist
        @{status='ok'; title=$title.Substring(0,[Math]::Min(512,$title.Length));
          artist=$artist.Substring(0,[Math]::Min(512,$artist.Length));
          state=[string]$info.PlaybackStatus} | ConvertTo-Json -Compress
    }
}
'''


class WindowsMediaSensor:
    interval = 12.0

    def __init__(self):
        self._lock = RLock()
        self._process = None
        self._cancel_generation = 0
        self._cached = None
        self._last = float('-inf')

    def cancel(self):
        with self._lock:
            self._cancel_generation += 1
            self._cached = None
            self._last = float('-inf')
            process = self._process
            if process is not None and process.poll() is None:
                # This Popen handle is the exact helper started here, never a looked-up PID.
                process.terminate()

    def read(self, *, permit=lambda: True, start_lock=None):
        if os.name != 'nt':
            return {'status': 'unavailable', 'text': 'Mídia do Windows indisponível'}
        with start_lock if start_lock is not None else nullcontext():
            with self._lock:
                if not permit():
                    return None
                if self._cached is not None and time.monotonic()-self._last < self.interval:
                    return dict(self._cached)
                generation = self._cancel_generation
                executable = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
                self._process = process = subprocess.Popen(
                    [str(executable), '-NoProfile', '-NonInteractive', '-Command', _SCRIPT],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            output, _ = process.communicate(timeout=5)
            if process.returncode != 0:
                result = {'status': 'unavailable', 'text': 'Mídia do Windows indisponível; não verificado'}
            else:
                data = json.loads(output.decode('utf-8-sig'))
                if data.get('status') not in {'ok', 'empty', 'protected'}:
                    raise ValueError('Invalid media response')
                if data.get('status') == 'empty':
                    result = {'status': 'empty', 'text': 'Nenhuma sessão de mídia do Windows'}
                elif data.get('status') == 'protected':
                    state = {'Playing': 'Tocando', 'Paused': 'Pausado', 'Stopped': 'Parado'}.get(data.get('state'), 'Mídia detectada')
                    result = {'status': 'protected', 'text': f'{state} · metadados ocultos por privacidade'}
                else:
                    state = {'Playing': 'Tocando', 'Paused': 'Pausado', 'Stopped': 'Parado'}.get(data.get('state'), 'Mídia detectada')
                    text = ' · '.join(safe_excerpt(data.get(key, ''), 80) for key in ('title', 'artist') if data.get(key))
                    result = {'status': 'ok', 'text': safe_excerpt(f'{state} · {text or "sem título informado"}', 180)}
                    from core.presence_sensors import _PRIVATE_TITLE
                    if _PRIVATE_TITLE.search(text):
                        result = {'status': 'protected', 'text': 'Metadados protegidos; título não exibido'}
        except (subprocess.TimeoutExpired, ValueError, OSError):
            if process.poll() is None:
                process.kill()
            process.communicate()
            result = {'status': 'unavailable', 'text': 'Consulta de mídia excedeu o tempo; não verificado'}
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
        with start_lock if start_lock is not None else nullcontext():
            with self._lock:
                if generation != self._cancel_generation or not permit():
                    return None
                self._cached = dict(result)
                self._last = time.monotonic()
                return result
