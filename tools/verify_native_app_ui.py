"""Real Nyx UI → permission dialog via QTest → Windows app → independent Win32.

Only the owned Nyx UI is driven. No personal Nyx instance is operated, and no
application is closed. Repetitions may observe an already-open app; this is a
diagnostic, not a cold-start/reset milestone gate.
"""
import argparse
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]

from bench.native_windows import APPS, fold, verify_app  # noqa: E402
from bench.environment import desktop_probe, ResourceSampler  # noqa: E402
from bench.checkpoint import atomic_write  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apps', nargs='+', choices=list(APPS), default=list(APPS))
    parser.add_argument('--runs', type=int, choices=range(3,11), default=3)
    parser.add_argument('--profile', choices=['conservative','normal','game','focus'], default='normal')
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('O relatório já existe; escolha outro --output para preservar os resultados.')
    environment = desktop_probe()
    if not environment['interactive_probe_passed']:
        parser.error('Foreground/clipboard indisponíveis; rode este comando em uma sessão Windows interativa.')
    from PyQt6 import sip
    from PyQt6.QtCore import QSettings, Qt, QTimer, QCoreApplication, QEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from audit.logger import AuditLogger
    from cli import build_registry
    from config import NyxConfig, PermissionMode
    from core.agent_loop import AgentLoop
    from core.llm_client import OllamaClient
    from core.ollama_service import ensure_local_ollama
    from core.resource_profiles import resource_profile_scope
    from core.task_runner import TaskRunner
    from ui.chat_store import ChatStore
    from ui.desktop import DesktopWindow
    from ui.overlay import OverlayWindow
    from ui.permission_dialog import PermissionDialog

    if not ensure_local_ollama().ready:
        raise RuntimeError('Ollama indisponível; nenhum modelo alternativo ativado.')
    client = OllamaClient(model=args.model)
    client.configure_thinking()
    warmup_started = time.monotonic()
    with resource_profile_scope(args.profile):
        client.converse('Bom dia, Nyx!')
    warmup_seconds = time.monotonic()-warmup_started
    artifacts = ROOT/'build/diagnostic'
    artifacts.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='native-app-ui-', dir=artifacts))
    registry = build_registry(NyxConfig(allowed_roots=[base], log_dir=base/'logs'))
    loop = AgentLoop(client, registry, AuditLogger(ROOT/'logs', session_id='native-ui-'+uuid4().hex),
                     mode=PermissionMode.ASSISTIDA)
    loop.task_runner = TaskRunner(loop)
    loop.task_runner.set_budget_profile('default')
    loop.task_runner.default_budget = (6,120)
    app = QApplication([])
    controller = OverlayWindow(loop)
    controller.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    controller.bubble.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    settings = QSettings(str(base/'desktop.ini'), QSettings.Format.IniFormat)
    for key,value in {'speech':False,'motion':False,'resource_profile':args.profile,
                      'idle_research':False,'conversation_initiative':False,'initiative_level':'off'}.items():
        settings.setValue(key,value)
    window = DesktopWindow(controller, ChatStore(base/'chats.db'), settings)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    window.set_page(0)
    current, approvals, denials = {}, [], []
    guard = loop.task_runner._guard
    def expected_open(action):
        params = action.get('params',{})
        target = params.get('app') or params.get('app_name') or params.get('name')
        return (action.get('type')=='ui_action' and params.get('action')=='open_app'
                and fold(target) in APPS[current['key']]['aliases'])
    def scoped_guard(tool,params):
        guard(tool,params)
        if tool!='ui_action' or (params.get('action') not in {'list_windows','list_installed_apps'}
                                and not expected_open({'type':tool,'params':params})):
            raise ValueError('BLOCKED_POLICY: o ensaio autoriza somente observação e abertura do aplicativo escolhido.')
    loop.task_runner._guard = scoped_guard
    def review_dialog():
        for dialog in app.topLevelWidgets():
            if not isinstance(dialog,PermissionDialog) or not dialog.isVisible() or dialog.property('bench_reviewed'):
                continue
            dialog.setProperty('bench_reviewed',True)
            approved = bool(current) and not dialog.is_destructive and expected_open(dialog.pending_action)
            (approvals if approved else denials).append({'type':dialog.pending_action.get('type'),
                                                       'action':dialog.pending_action.get('params',{}).get('action')})
            QTest.mouseClick(dialog.btn_approve if approved else dialog.btn_deny,Qt.MouseButton.LeftButton)
    reviewer = QTimer(window)
    reviewer.setInterval(50)
    reviewer.timeout.connect(review_dialog)
    reviewer.start()
    report = {'scope':'owned production Qt UI, real permission-dialog clicks, real model, independent Win32',
              'environment':environment,'model':args.model,'profile':args.profile,'runs':args.runs,
              'warmup_excluded_s':warmup_seconds,
              'milestone_complete':False,'rows':[],
              'limitations':['No personal apps are closed; state is not reset between repetitions.',
                             'Personal window titles and model text remain only in local ignored traces.',
                             'This does not validate logged-in app functionality, voice, or all 15 apps.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(args.output,report)
    timed_out = False
    try:
        for run in range(1,args.runs+1):
            for key in args.apps:
                current['key'] = key
                approvals.clear()
                denials.clear()
                before = verify_app(key)
                window.new_chat()
                app.processEvents()
                started = time.monotonic()
                with ResourceSampler() as sampler:
                    window.composer.setPlainText(APPS[key]['prompt'])
                    window.send_prompt()
                    deadline = started+135
                    while window._busy and time.monotonic()<deadline:
                        app.processEvents()
                        time.sleep(.005)
                    app.processEvents()
                    timed_out = window._busy
                    if timed_out:
                        controller.cancel_task()
                    verdict = verify_app(key)
                task_id = loop.task_runner.task_id
                events = [row for row in loop.audit.read_all() if row.get('task_id')==task_id]
                finished = next((row['state'] for row in reversed(events) if row['event']=='task_finished'),None)
                claimed_verified = any(s['tool']=='ui_action' and s['params'].get('action')=='open_app' and s['verified']
                                       for s in loop.task_runner.steps)
                passed = verdict['ok'] and finished=='finished' and not denials and not timed_out
                row = {'app':key,'run':run,'ok':passed,'elapsed_s':round(time.monotonic()-started,3),
                       'already_visible_before':before['ok'],'verifier':verdict,'workflow_state':finished,
                       'confirmations_approved':len(approvals),'confirmations_denied':len(denials),
                       'false_success':bool(claimed_verified and not verdict['ok']),
                       'error_code':'TIMEOUT' if timed_out else None if passed else 'UNVERIFIED',
                       'actions':len(loop.task_runner.steps),'resources':sampler.report(),
                       'trace_path':f'logs/traces/{task_id}.jsonl'}
                report['rows'].append(row)
                atomic_write(args.output,report)
                print(key,run,'PASS' if passed else 'FAIL',row['elapsed_s'],flush=True)
                if timed_out:
                    raise TimeoutError('A tarefa não encerrou no prazo; relatório parcial preservado, sem repetir a abertura.')
        report['permission_dialog_exercised'] = any(row['confirmations_approved'] for row in report['rows'])
        report['passed'] = all(row['ok'] and not row['false_success'] for row in report['rows'])
        atomic_write(args.output,report)
    finally:
        reviewer.stop()
        controller.cancel_task() if timed_out else None
        window.close()
        if not controller._prompt_pool.waitForDone(15000):
            raise RuntimeError('Worker não encerrou; nenhuma nova tarefa será iniciada.')
        registry.browser_session.close()
        window.deleteLater()
        controller.deleteLater()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        sip.delete(app)
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
