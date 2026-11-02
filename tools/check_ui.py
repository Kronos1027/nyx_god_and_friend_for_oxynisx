"""Inspect the real HUD with isolated state; screenshots remain in ignored build/."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def contrast(first, second):
    def luminance(color):
        rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        rgb = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * weight for v, weight in zip(rgb, (.2126, .7152, .0722), strict=True))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + .05) / (a + .05)


def inspect_widgets(window):
    from PyQt6.QtWidgets import QLabel, QPushButton, QTabBar
    findings = []
    for widget in window.findChildren((QLabel, QPushButton, QTabBar)):
        if not widget.isVisible() or widget.width() <= 0:
            continue
        if isinstance(widget, QTabBar):
            for index in range(widget.count()):
                if widget.fontMetrics().horizontalAdvance(widget.tabText(index)) > widget.tabRect(index).width():
                    findings.append({'kind': 'tab_width', 'text': widget.tabText(index)})
            continue
        text = widget.text().replace('&', '')
        if not text or isinstance(widget, QLabel) and (widget.wordWrap() or '<' in text):
            continue
        # contentsRect incorporates QSS padding for labels; button padding requires sizeHint.
        required = widget.fontMetrics().horizontalAdvance(text)
        available = widget.contentsRect().width()
        if isinstance(widget, QPushButton):
            available -= 24 + (widget.iconSize().width() + 4 if not widget.icon().isNull() else 0)
        if required > available + 2:
            findings.append({'kind': 'text_width', 'text': text, 'required': required, 'available': available})
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    from PyQt6.QtCore import QSettings, QTimer, Qt
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
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
    from ui.tokens import hud_design_tokens

    class SilentVoice:
        enabled = False
        def speak(self, text): pass
        def stop_current(self): pass
        def shutdown(self): pass

    started = time.perf_counter()
    audio.tts.TextToSpeech = SilentVoice
    app = QApplication([])
    scale = os.environ.get('QT_SCALE_FACTOR', '1')
    destination = ROOT / 'build/previews' / ('hud-' + scale)
    destination.mkdir(parents=True, exist_ok=True)
    state = ROOT / 'build/preview-state'
    state.mkdir(parents=True, exist_ok=True)
    report = {'scale': scale, 'platform': app.platformName(), 'captures': [], 'smoke': {}, 'contrast': {}}
    for theme, palette in hud_design_tokens()['themes'].items():
        measured = {f'{fg}/{bg}': round(contrast(palette[fg], palette[bg]), 3)
                    for fg in ('text', 'muted', 'gold', 'teal', 'red')
                    for bg in ('ink', 'surface1', 'surface2')}
        measured.update({f'on{key.title()}/{key}': round(contrast(palette['on'+key.title()], palette[key]), 3)
                         for key in ('gold', 'teal', 'red')})
        report['contrast'][theme] = measured
    report['contrast_passed'] = all(value >= 4.5 for theme in report['contrast'].values() for value in theme.values())
    with tempfile.TemporaryDirectory(prefix='hud-qa-', dir=state) as directory:
        directory = Path(directory)
        registry = ToolRegistry()
        registry.reminder_scheduler = ReminderScheduler(directory/'reminders.db')
        llm = OfflineLLM()
        loop = AgentLoop(llm, registry, AuditLogger(directory/'logs', session_id='hud-qa'))
        controller = OverlayWindow(loop)
        window = DesktopWindow(controller, ChatStore(directory/'chat.db'),
                               QSettings(str(directory/'ui.ini'), QSettings.Format.IniFormat))
        window.motion_check.setChecked(False)
        window.resize(1180, 760)
        window.show()
        app.processEvents()
        report['native_style'] = window._native_style
        report['first_paint_s'] = round(time.perf_counter()-started, 4)
        process = psutil.Process()
        cpu_before = sum(process.cpu_times()[:2])
        idle_started = time.perf_counter()
        while time.perf_counter()-idle_started < 10:
            app.processEvents()
            time.sleep(.01)
        report['rss_mib'] = round(process.memory_info().rss/1024**2, 2)
        report['idle_cpu_percent'] = round((sum(process.cpu_times()[:2])-cpu_before)/(time.perf_counter()-idle_started)*100, 3)

        def capture(name):
            app.processEvents()
            path = destination/(name+'.png')
            if not window.grab().save(str(path)):
                raise RuntimeError('Captura não gravada')
            report['captures'].append({'name': name, 'findings': inspect_widgets(window)})

        for theme in ('midnight', 'daylight'):
            window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
            window.set_page(0)
            capture(theme+'-chat')
            window.set_page(1)
            capture(theme+'-agenda')
            window.set_page(2)
            for index in range(window.settings_tabs.count()):
                window.settings_tabs.setCurrentIndex(index)
                capture(f'{theme}-settings-{index}')
            window.set_page(3)
            for index in range(window.learning_tabs.count()):
                window.learning_tabs.setCurrentIndex(index)
                capture(f'{theme}-learning-{index}')
            window.open_palette()
            app.processEvents()
            window.palette.grab().save(str(destination/(theme+'-palette.png')))
            window.palette.reject()
            pending = {'type':'ui_action','params':{'action':'open_app','app':'Aplicativo de demonstração'}}
            def review(theme=theme):
                capture(theme+'-confirm')
                QTest.mouseClick(window._pending_confirm_card.btn_deny, Qt.MouseButton.LeftButton)
            QTimer.singleShot(0,review)
            report['smoke'][theme+'_deny'] = not window.request_confirmation(pending)

        pending = {'type':'ui_action','params':{'action':'open_app','app':'Demonstração'}}
        QTimer.singleShot(0,lambda:QTest.mouseClick(window._pending_confirm_card.btn_approve,Qt.MouseButton.LeftButton))
        report['smoke']['approve'] = window.request_confirmation(pending)
        window.speech_check.setChecked(False)
        was_initiative = window.initiative_check.isChecked()
        QTest.mouseClick(window.private_button, Qt.MouseButton.LeftButton)
        report['smoke']['private_pause'] = window._context.is_paused and not window.initiative_check.isChecked()
        QTest.mouseClick(window.private_button, Qt.MouseButton.LeftButton)
        report['smoke']['private_restore'] = not window.speech_check.isChecked() and window.initiative_check.isChecked()==was_initiative
        llm.queue(json.dumps({'emotion':'talk','action':{'type':'none','params':{}},'speech_output':'Resposta de demonstração da interface.'}))
        window.composer.setPlainText('Demonstração de interação')
        QTest.keyClick(window.composer, Qt.Key.Key_Return)
        deadline = time.monotonic()+5
        while window._busy and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        report['smoke']['send'] = not window._busy and any('Resposta de demonstração' in item['content'] for item in window.store.messages(window.chat_id))
        QTest.mouseClick(window.emergency_button, Qt.MouseButton.LeftButton)
        report['smoke']['stop'] = registry.control.is_cancelled()
        controller.resume_tools()
        window.activateWindow()
        window.composer.setFocus()
        app.processEvents()
        QTest.keyClick(window.composer, Qt.Key.Key_Escape)
        QTest.keyClick(window.composer, Qt.Key.Key_Escape)
        app.processEvents()
        report['smoke']['escape_escape_stop'] = registry.control.is_cancelled()
        window.hide()
        app.processEvents()
        report['smoke']['hidden_polling_stopped'] = not any(t.isActive() for t in (window.telemetry_timer, window.research_timer, window.initiative_timer))
        report['backup_timer_preserved'] = window.backup_timer.isActive()
        window.close()
        app.processEvents()
    report['passed_interactions'] = all(report['smoke'].values())
    report['text_findings'] = sum(len(c['findings']) for c in report['captures'])
    target = args.output or destination/'report.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'captures','contrast'}},ensure_ascii=False))
    return 0 if report['passed_interactions'] and report['contrast_passed'] and not report['text_findings'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
