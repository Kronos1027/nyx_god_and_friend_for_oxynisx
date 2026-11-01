"""Real model through isolated Nyx UI; private temporary data and voice disabled.

Measures Qt delivery and label update, not a physical display or voice latency.
No personal conversation, browser profile or running Nyx process is controlled.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from PyQt6.QtCore import QSettings, Qt, QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtGui import QFontDatabase, QFont  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6 import sip  # noqa: E402
from audit.logger import AuditLogger  # noqa: E402
from cli import build_registry  # noqa: E402
from config import NyxConfig  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OllamaClient  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.task_runner import TaskRunner  # noqa: E402
from ui.chat_store import ChatStore  # noqa: E402
from ui.desktop import DesktopWindow  # noqa: E402
from ui.overlay import OverlayWindow  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prompt', default='Bom dia, Nyx! Como você está?')
    args = parser.parse_args()
    if not ensure_local_ollama().ready:
        raise RuntimeError('Ollama indisponível.')
    output = ROOT / 'build/previews'
    output.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='real-conversation-', dir=output))
    registry = build_registry(NyxConfig(allowed_roots=[base], log_dir=base / 'logs'))
    client = OllamaClient(model='qwen3.5:4b')
    client.configure_thinking()
    client.generate('Bom dia, Nyx!', task_tools=[])  # warmup is not included in UI latency
    app = QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
    app.setFont(QFont('Segoe UI', 10))
    settings = QSettings(str(base / 'desktop.ini'), QSettings.Format.IniFormat)
    settings.setValue('speech', False)
    settings.setValue('motion', False)
    settings.setValue('resource_profile', 'conservative')
    loop = AgentLoop(client, registry, AuditLogger(base / 'logs'))
    loop.task_runner = TaskRunner(loop)
    controller = OverlayWindow(loop)
    controller.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window = DesktopWindow(controller, ChatStore(base / 'chats.db'), settings)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    window.set_page(0)
    app.processEvents()
    chunks, first = [], []
    started = time.monotonic()
    def progress(event):
        if event['phase'] == 'conversation_delta':
            chunks.append(event['text'])
            if not first:
                first.append({'elapsed_s': time.monotonic() - started, 'label': window._streaming_body.text()})
                window.grab().save(str(output / 'conversation-first-delta.png'))
    controller.task_progress.connect(progress)
    window.composer.setPlainText(args.prompt)
    window.send_prompt()
    deadline = time.monotonic() + client.timeout + 10
    while window._busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    text = loop.history[-1]['content'] if loop.history else ''
    report = {'ui': 'isolated production Qt window, not physical display', 'real_model': client.model,
              'input': args.prompt, 'voice_enabled': controller.tts.enabled, 'first_delta': first[0] if first else None,
              'elapsed_s': time.monotonic() - started, 'response': text, 'actions': len(loop.task_runner.steps),
              'generations': [row['attempts'] for row in loop.audit.read_all() if row['event'] == 'model_generation'],
              'passed': bool(first) and not window._busy and bool(text) and ''.join(chunks) == text
                        and not loop.task_runner.steps and first[0]['label'] == chunks[0]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    window.grab().save(str(output / 'conversation-complete.png'))
    window.close()
    if not controller._prompt_pool.waitForDone(10000):
        raise RuntimeError('Worker da conversa não encerrou; prévia não será qualificada.')
    registry.browser_session.close()
    window.deleteLater()
    controller.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    sip.delete(app)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
