"""Fresh-process HUD first-frame probe; owned synthetic state, no model or personal UI."""
from __future__ import annotations

import time

BOOT = time.perf_counter()

import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import cProfile  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def worker(platform, idle_seconds):
    os.environ['QT_QPA_PLATFORM'] = platform
    before_imports = time.perf_counter()
    from PyQt6.QtCore import QEvent, QObject, QSettings, Qt
    from PyQt6.QtWidgets import QApplication
    import psutil
    import audio.tts
    from audit.logger import AuditLogger
    from core.agent_loop import AgentLoop
    from core.llm_client import OfflineLLM
    from core.scheduler import ReminderScheduler
    from tools.registry import ToolRegistry
    from ui.chat_store import ChatStore
    from ui.desktop import DesktopWindow
    from ui.overlay import OverlayWindow
    imports = time.perf_counter() - before_imports

    class SilentVoice:
        enabled = False
        def speak(self, text): pass
        def stop_current(self): pass
        def shutdown(self): pass

    audio.tts.TextToSpeech = SilentVoice
    app_started = time.perf_counter()
    app = QApplication([])
    app_ready = time.perf_counter()
    methods = {}
    for name in ('_build_center','_build_chat_page','_build_agenda_page','_build_settings_page',
                 '_build_evolution_page','_build_companion','_apply_preferences','_restore_layout',
                 '_refresh_status','_build_sidebar','_build_activity','_reload_chats','activate_chat'):
        original = getattr(DesktopWindow, name)
        def measured(self, *args, _name=name, _original=original, **kwargs):
            started = time.perf_counter()
            try:
                return _original(self, *args, **kwargs)
            finally:
                methods[_name] = methods.get(_name, 0) + time.perf_counter() - started
        setattr(DesktopWindow, name, measured)
    first_paint = []
    class PaintObserver(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint and not first_paint:
                first_paint.append(time.perf_counter())
            return False
    state = ROOT / 'build/preview-state'
    state.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hud-first-frame-', dir=state) as temporary:
        directory = Path(temporary)
        registry = ToolRegistry()
        registry.reminder_scheduler = ReminderScheduler(directory/'reminders.db')
        loop = AgentLoop(OfflineLLM(), registry, AuditLogger(directory/'logs', session_id='hud-first-frame'))
        controller_started = time.perf_counter()
        controller = OverlayWindow(loop)
        controller.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        controller_seconds = time.perf_counter() - controller_started
        settings = QSettings(str(directory/'ui.ini'), QSettings.Format.IniFormat)
        for key, value in {'speech':False, 'motion':False, 'idle_research':False,
                           'conversation_initiative':False, 'initiative_level':'off'}.items():
            settings.setValue(key, value)
        constructor_started = time.perf_counter()
        ram_before = psutil.virtual_memory().available
        faults_before = getattr(psutil.Process().memory_info(),'num_page_faults',None)
        profiler = cProfile.Profile()
        profiler.enable()
        window = DesktopWindow(controller, ChatStore(directory/'chat.db'), settings)
        profiler.disable()
        constructor_seconds = time.perf_counter() - constructor_started
        import pstats
        stats = pstats.Stats(profiler).stats
        slow = sorted(stats.items(),key=lambda item:item[1][2],reverse=True)[:12]
        window.setWindowTitle('Nyx — medição isolada de primeira pintura')
        observer = PaintObserver(window)
        window.installEventFilter(observer)
        show_started = time.perf_counter()
        window.show()
        show_seconds = time.perf_counter() - show_started
        deadline = time.monotonic() + 10
        while not first_paint and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.001)
        ready = time.perf_counter()
        process = psutil.Process()
        cpu_started = sum(process.cpu_times()[:2])
        idle_started = time.perf_counter()
        while time.perf_counter() - idle_started < idle_seconds:
            app.processEvents()
            time.sleep(.01)
        rss = process.memory_info().rss / 1024**2
        cpu = (sum(process.cpu_times()[:2]) - cpu_started)/(time.perf_counter()-idle_started)*100
        report = {'platform':app.platformName(), 'imports_s':imports,
                  'application_init_s':app_ready-app_started, 'controller_s':controller_seconds,
                  'constructor_s':constructor_seconds, 'show_s':show_seconds,
                  'system_ram_available_before_constructor_bytes':ram_before,
                  'system_ram_available_after_frame_bytes':psutil.virtual_memory().available,
                  'process_page_faults_before_constructor':faults_before,
                  'process_page_faults_after_frame':getattr(process.memory_info(),'num_page_faults',None),
                  'profiled_constructor':True,
                  'slow_constructor_self_calls':[{'module':Path(key[0]).name,'function':key[2],
                      'calls':value[1],'self_s':value[2],'cumulative_s':value[3]} for key,value in slow],
                  'first_paint_from_process_s':first_paint[0]-BOOT if first_paint else None,
                  'first_paint_from_app_s':first_paint[0]-app_started if first_paint else None,
                  'first_event_batch_from_app_s':ready-app_started,
                  'rss_mib':rss, 'idle_cpu_percent':cpu, 'idle_sample_seconds':idle_seconds,
                  'constructor_methods_s':methods,
                  'deferred_panels':len(window._deferred_pages) if hasattr(window,'_deferred_pages') else 0,
                  'unbuilt_panels':sum(callable(page) for page in window._deferred_pages.values()) if hasattr(window,'_deferred_pages') else 0,
                  'studio_imported': 'ui.workspace_window' in sys.modules,
                  'paint_observed':bool(first_paint), 'native_style':window._native_style,
                  'scope':'Owned synthetic HUD; paint event start, not physical monitor/capture proof; no model.'}
        window.close()
        app.processEvents()
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=['windows','offscreen'], default='windows')
    parser.add_argument('--runs', type=int, choices=range(1,4), default=3)
    parser.add_argument('--idle-seconds', type=float, default=2)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.platform, max(1,min(args.idle_seconds,10)))), flush=True)
        return 0
    if not args.output or args.output.exists():
        parser.error('Escolha um relatório novo --output.')
    rows = []
    for run in range(1,args.runs+1):
        result = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',
            '--platform',args.platform,'--idle-seconds',str(args.idle_seconds)],
            capture_output=True,text=True,encoding='utf-8',timeout=45,check=True)
        row = json.loads(result.stdout.strip().splitlines()[-1])
        row['run'] = run
        rows.append(row)
        print(json.dumps(row),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'runs':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(row['paint_observed'] for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
