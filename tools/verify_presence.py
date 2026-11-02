"""Real Windows/Qt/GSMTC fixtures; publish only booleans and resource measurements."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

_MEDIA_FIXTURE = r'''
param([string]$AudioPath, [string]$Title)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$playerType = [Windows.Media.Playback.MediaPlayer, Windows.Media.Playback, ContentType=WindowsRuntime]
$sourceType = [Windows.Media.Core.MediaSource, Windows.Media.Core, ContentType=WindowsRuntime]
$itemType = [Windows.Media.Playback.MediaPlaybackItem, Windows.Media.Playback, ContentType=WindowsRuntime]
$item = $itemType::new($sourceType::CreateFromUri([Uri]::new($AudioPath)))
$properties = $item.GetDisplayProperties()
$properties.Type = [Windows.Media.MediaPlaybackType]::Music
$properties.MusicProperties.Title = $Title
$properties.MusicProperties.Artist = 'Nyx native fixture'
$item.ApplyDisplayProperties($properties)
$player = New-Object $playerType
$player.Volume = 0
$player.IsLoopingEnabled = $true
$player.Source = $item
$player.Play()
'READY'
Start-Sleep -Seconds 90
$player.Dispose()
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--single-run', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Este ensaio exige Windows real.')
    if args.runs > 1 and not args.single_run:
        work = ROOT/'build/presence-verify'
        work.mkdir(parents=True, exist_ok=True)
        rows = []
        for run in range(1, args.runs+1):
            output = work/f'fresh-{run}.json'
            subprocess.run([sys.executable, str(Path(__file__).resolve()), '--single-run',
                                    '--runs', '1', '--output', str(output)], check=True, timeout=150)
            row = json.loads(output.read_text(encoding='utf-8'))['runs'][0]
            row['run'] = run
            rows.append(row)
        checks = [value for row in rows for value in row.values() if type(value) is bool]
        report = {'scope': 'Three fresh Windows processes; native foreground/owned process fixture/GSMTC and production HUD. No LLM, actual game workload, or audible output qualification.',
                  'runs': rows, 'checks_passed': sum(checks), 'checks_total': len(checks),
                  'ui_rss_median_mib': statistics.median(row['ui_rss_mib'] for row in rows),
                  'ui_idle_cpu_max_percent': max(row['ui_idle_cpu_percent'] for row in rows)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        raise SystemExit(0 if all(checks) else 1)
    from ctypes import wintypes
    from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
    from PyQt6.QtWidgets import QApplication
    import psutil
    import audio.tts
    from audit.logger import AuditLogger
    from core.agent_loop import AgentLoop
    from core.llm_client import OfflineLLM
    from core.presence_sensors import active_window, known_games, process_inventory
    from core.scheduler import ReminderScheduler
    from tools.registry import ToolRegistry
    from ui.chat_store import ChatStore
    from ui.desktop import DesktopWindow
    from ui.overlay import OverlayWindow

    class SilentVoice:
        enabled = False
        def speak(self, text): pass
        def stop_current(self): pass
        def shutdown(self): pass
    audio.tts.TextToSpeech = SilentVoice
    app = QApplication([])
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    powershell = str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
    work = ROOT/'build/presence-verify'
    work.mkdir(parents=True, exist_ok=True)
    rows = []
    for run in range(1, args.runs+1):
        with tempfile.TemporaryDirectory(prefix='run-', dir=work) as directory:
            directory = Path(directory)
            wav = directory/'silence.wav'
            with wave.open(str(wav), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(b'\0\0'*8000*15)
            fixture = directory/'media.ps1'
            fixture.write_text(_MEDIA_FIXTURE, encoding='utf-8')
            compiler = directory/'compile.ps1'
            compiler.write_text(
                "param([string]$Output)\nAdd-Type -TypeDefinition 'using System; using System.Threading; "
                "public static class Fixture { public static void Main() { Thread.Sleep(90000); } }' "
                "-OutputAssembly $Output -OutputType ConsoleApplication\n", encoding='utf-8')
            native = directory/'cs2.exe'
            subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-File', str(compiler), str(native)],
                           check=True, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            marker = f'Nyx fixture de percepção {run}'
            media_title = f'NYX PRESENCE LOCAL FIXTURE {run}'
            children = []
            window = None
            started = time.perf_counter()
            row = {'run': run}
            try:
                game = subprocess.Popen([str(native)], creationflags=subprocess.CREATE_NO_WINDOW)
                children.append((game, psutil.Process(game.pid).create_time()))
                media = subprocess.Popen([powershell, '-NoProfile', '-NonInteractive', '-File', str(fixture), str(wav), media_title],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                children.append((media, psutil.Process(media.pid).create_time()))
                time.sleep(1.8)
                registry = ToolRegistry()
                registry.reminder_scheduler = ReminderScheduler(directory/'schedule.db')
                controller = OverlayWindow(AgentLoop(OfflineLLM(), registry, AuditLogger(directory/'logs', session_id='presence')))
                settings = QSettings(str(directory/'ui.ini'), QSettings.Format.IniFormat)
                settings.setValue('resource_profile', 'normal')
                settings.setValue('speech', False)
                settings.setValue('motion', False)
                settings.setValue('conversation_initiative', False)
                settings.setValue('idle_research', False)
                window = DesktopWindow(controller, ChatStore(directory/'chat.db'), settings)
                window.setWindowTitle(marker)
                window.show()
                window.raise_()
                window.activateWindow()
                deadline = time.monotonic()+3
                hwnd = int(window.winId())
                while user32.GetForegroundWindow() != hwnd and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                text = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, text, len(text))
                row['independent_window'] = bool(user32.IsWindowVisible(hwnd) and user32.GetForegroundWindow() == hwnd and text.value == marker)
                row['off_by_default'] = all(not window.sensor_checks[key].isChecked() for key in ('active_window', 'process_inventory', 'media', 'games'))
                row['window_observed'] = row['independent_window'] and marker in active_window()['text']
                inventory = process_inventory()
                row['independent_game_process'] = (psutil.Process(game.pid).name().casefold() == 'cs2.exe'
                                                   and psutil.Process(game.pid).create_time() == children[0][1])
                row['inventory_observed'] = 'cs2.exe' in [name.casefold() for name in inventory['names']]
                row['game_candidate_observed'] = row['independent_game_process'] and 'Counter-Strike 2' in known_games()['text']
                for sensor in ('active_window', 'process_inventory', 'media', 'games'):
                    window.sensor_checks[sensor].click()
                window._refresh_presence()
                deadline = time.monotonic()+8
                while media_title not in window.agora.fields['media'].text() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                row['hud_window'] = marker in window.agora.fields['window'].text()
                row['hud_media'] = media_title in window.agora.fields['media'].text() and 'Tocando' in window.agora.fields['media'].text()
                row['hud_game'] = 'Counter-Strike 2' in window.agora.fields['game'].text()
                row['hud_processes'] = 'nomes de processos' in window.agora.fields['processes'].text()
                row['native_window_hooks_registered'] = (window._presence._window is not None
                                                         and len(window._presence._window._hooks) == 2)
                window.resource_profile_combo.setCurrentIndex(window.resource_profile_combo.findData('game'))
                window._refresh_presence()
                deadline = time.monotonic()+4
                while 'Pausado no perfil Jogo/Live' not in window.agora.fields['media'].text() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.01)
                row['live_hides_title'] = marker not in window.agora.fields['window'].text()
                row['live_pauses_media_inventory'] = all('Pausado no perfil Jogo/Live' in window.agora.fields[key].text()
                                                         for key in ('media', 'processes'))
                row['live_no_title_hooks'] = not window._presence._window._hooks
                window.resource_profile_combo.setCurrentIndex(window.resource_profile_combo.findData('normal'))
                window._refresh_presence()
                permissions = window._context.permissions()
                access = window._context.access_history()
                with window._context.connect() as db:
                    before = db.execute('SELECT COUNT(*) FROM context_events').fetchone()[0]
                snapshot = {'generation': window._presence._generation, 'observed_at': time.monotonic(),
                            'fields': {'window': {'status': 'ok', 'text': 'LATE PRIVATE CONTENT'}}}
                window.private_button.setChecked(True)
                window._presence_done(snapshot)
                app.processEvents()
                row['private_clears_hud'] = all('Privado' in window.agora.fields[key].text() for key in ('window', 'processes', 'media', 'game'))
                row['private_preserves_consent'] = permissions == window._context.permissions()
                row['private_unhooks_window_events'] = not window._presence._window._hooks
                with window._context.connect() as db:
                    after = db.execute('SELECT COUNT(*) FROM context_events').fetchone()[0]
                row['no_context_content_recorded'] = before == after == 0 and access == window._context.access_history()
                window.private_button.setChecked(False)
                window._presence_done(snapshot)
                row['old_sample_rejected_after_resume'] = 'LATE PRIVATE CONTENT' not in window.agora.fields['window'].text()
                warm = time.monotonic()
                while time.monotonic()-warm < 2:
                    app.processEvents()
                    time.sleep(.025)
                process = psutil.Process()
                row['ui_rss_mib'] = round(process.memory_info().rss/1024**2, 3)
                cpu_before = process.cpu_times()
                tick = time.monotonic()
                while time.monotonic()-tick < 10:
                    app.processEvents()
                    time.sleep(.025)
                cpu_after = process.cpu_times()
                row['ui_idle_cpu_percent'] = round(100*((cpu_after.user-cpu_before.user)+(cpu_after.system-cpu_before.system))/(time.monotonic()-tick), 3)
                row['elapsed_s'] = round(time.perf_counter()-started, 3)
            except Exception as exc:
                row['error_type'] = type(exc).__name__
            finally:
                if window is not None:
                    controller._reminder_timer.stop()
                    window.close()
                    app.processEvents()
                    window.deleteLater()
                    controller.deleteLater()
                    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                for process, created in reversed(children):
                    try:
                        if process.poll() is None and psutil.Process(process.pid).create_time() == created:
                            process.terminate()
                        process.communicate(timeout=5)
                    except (psutil.NoSuchProcess, subprocess.TimeoutExpired):
                        pass
            rows.append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)
    checks = [value for row in rows for value in row.values() if type(value) is bool]
    report = {'scope': 'Real Windows foreground, owned renamed process fixture, silent MediaPlayer GSMTC metadata and production HUD; no LLM or audible output qualification.',
              'runs': rows, 'checks_passed': sum(checks), 'checks_total': len(checks),
              'ui_rss_median_mib': statistics.median(row['ui_rss_mib'] for row in rows if 'ui_rss_mib' in row),
              'ui_idle_cpu_max_percent': max(row['ui_idle_cpu_percent'] for row in rows if 'ui_idle_cpu_percent' in row)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    raise SystemExit(0 if len(rows) == args.runs and all(checks) and not any('error_type' in row for row in rows) else 1)


if __name__ == '__main__':
    main()
