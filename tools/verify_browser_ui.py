"""Ten real browser tasks via production HUD, model and confirmation cards."""
import argparse
from pathlib import Path
import sys
import tempfile
import threading
import time
import socket
import gc
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'src')]

from bench.browser_fixture import BrowserFixture  # noqa: E402
from bench.browser_observer import BrowserObserver, verify_fixture, claims_completion  # noqa: E402
from bench.checkpoint import atomic_write, runtime_fingerprint  # noqa: E402
from bench.environment import desktop_probe, ResourceSampler  # noqa: E402
from bench.owned_runtime import isolated_runtime  # noqa: E402


def trial(app, client, profile, base, number, run, headless, visible_ui):
    from PyQt6.QtCore import QSettings, Qt, QTimer, QCoreApplication, QEvent
    from PyQt6.QtTest import QTest
    from audit.logger import AuditLogger
    from core.agent_loop import AgentLoop
    from core.task_runner import TaskRunner
    from tools.browser_tool import BrowserSession, make_browser_tool_func
    from tools.browser_contract import browser_tool_spec
    from tools.registry import ToolRegistry
    from ui.chat_store import ChatStore
    from ui.desktop import DesktopWindow
    from ui.hud.confirm_card import ConfirmCard
    from ui.overlay import OverlayWindow

    work = base/f'browser-{number:02}-{run}'
    work.mkdir()
    download = work/'download.txt'
    registry = ToolRegistry()
    session = BrowserSession(headless=headless,persistent_profile=work/'profile',control=registry.control,timeout=10)
    registry.browser_session = session
    registry.register(browser_tool_spec(),make_browser_tool_func(session,[work]))
    loop = AgentLoop(client,registry,AuditLogger(ROOT/'logs',session_id='browser-ui-'+uuid4().hex))
    runner = loop.task_runner = TaskRunner(loop)
    controller = OverlayWindow(loop)
    controller.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    controller.bubble.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    settings = QSettings(str(work/'desktop.ini'),QSettings.Format.IniFormat)
    for key,value in {'speech':False,'motion':False,'resource_profile':profile,'task_budget':'extended',
                      'idle_research':False,'conversation_initiative':False,'initiative_level':'off'}.items():
        settings.setValue(key,value)
    window = DesktopWindow(controller,ChatStore(work/'chats.db'),settings)
    if not visible_ui:
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.setWindowTitle('Nyx — ensaio isolado navegador')
    window.show()
    runner.default_budget = (12,120)
    approvals, denied, media, samples = [], [], [], []
    stop, observer_errors = threading.Event(), []
    timed_out, restarted = False, False
    row = {}
    with BrowserFixture(number,run).serve() as fixture:
        def scrub(value):
            for prefix,label in ((work,'<WORK>'),(base,'<RUN_ROOT>'),(ROOT,'<PROJECT>')):
                value = value.replace(str(prefix),label).replace(prefix.as_posix(),label)
            return value.replace(fixture.base,'<FIXTURE>')
        def scoped(params):
            if params.get('action') in {'open','navigate','new_tab','download'}:
                url = str(params.get('url',''))
                if url != 'about:blank' and urlsplit(url).netloc != urlsplit(fixture.base).netloc:
                    return False
            if params.get('action')=='download':
                target = Path(params.get('path',''))
                if not target.is_absolute():
                    target = work/target
                if target.resolve()!=download.resolve():
                    return False
            return True
        original_guard = runner._guard
        def guard(tool,params):
            if tool!='browser' or not scoped(params):
                raise ValueError('BLOCKED_POLICY: ensaio limitado à fixture e ao arquivo escolhido.')
            original_guard(tool,params)
        runner._guard = guard
        def review():
            for card in window.findChildren(ConfirmCard):
                if not card.isVisible() or card.property('bench_reviewed'):
                    continue
                card.setProperty('bench_reviewed',True)
                action = card.pending_action
                approved = action.get('type')=='browser' and scoped(action.get('params',{}))
                (approvals if approved else denied).append(action.get('params',{}).get('action'))
                QTest.mouseClick(card.btn_approve if approved else card.btn_deny,Qt.MouseButton.LeftButton)
        timer = QTimer(window)
        timer.setInterval(40)
        timer.timeout.connect(review)
        timer.start()
        def observe():
            while not stop.wait(.3):
                try:
                    if not session.started:
                        continue
                    state = BrowserObserver(session._port).snapshot()
                    samples[:] = state
                    for page in state:
                        if page.get('url','').startswith(fixture.base+'/') and page.get('media'):
                            media.append(page['media'])
                except Exception as exc:
                    observer_errors.append(type(exc).__name__)
        observer = threading.Thread(target=observe,daemon=True)
        started = time.monotonic()
        try:
            if number == 7:
                session.open(fixture.base+'/tab/origin')
                session.new_tab(fixture.base+'/tab/destination')
            elif number == 10:
                session.open(fixture.base+'/session/seed')
                old_port = session._port
                session.close()
                try:
                    with socket.create_connection(('127.0.0.1',old_port),timeout=.5):
                        restarted = False
                except OSError:
                    restarted = True
            observer.start()
            with ResourceSampler() as sampler:
                started = time.monotonic()
                window.composer.setPlainText(fixture.prompt(download))
                window.send_prompt()
                deadline = started+130
                while window._busy and time.monotonic()<deadline:
                    app.processEvents()
                    time.sleep(.005)
                app.processEvents()
                timed_out = window._busy
                if timed_out:
                    controller.cancel_task()
                    deadline = time.monotonic()+70
                    while window._busy and time.monotonic()<deadline:
                        app.processEvents()
                        time.sleep(.01)
                stop.set()
                observer.join(5)
                if session.started:
                    samples[:] = BrowserObserver(session._port).snapshot()
                speech = loop.history[-1]['content'] if loop.history else ''
                verdict = verify_fixture(fixture,samples,speech,download,media,restarted=restarted)
            events = [event for event in loop.audit.read_all() if event.get('task_id')==runner.task_id]
            state = next((event['state'] for event in reversed(events) if event['event']=='task_finished'),None)
            passed = verdict['ok'] and state=='finished' and not denied and not timed_out
            false_success = not verdict['ok'] and state=='finished' and claims_completion(speech)
            row = {'id':f'browser-{number:02}','category':'browser','run':run,
                'ok':bool(passed),'status':'PASS' if passed else 'FAIL','false_success':bool(false_success),
                'elapsed_s':round(time.monotonic()-started,3),'verifier':verdict,'workflow_state':state,
                'actions':len(runner.steps),'confirmations_approved':len(approvals),'confirmations_denied':len(denied),
                'error_code':None if passed else 'RESOURCE_PRESSURE' if runner.resource_pressure else 'TIMEOUT' if timed_out else 'UNVERIFIED',
                'response':scrub(speech),
                'prompt':scrub(fixture.prompt(download)),
                'resources':sampler.report(),'trace_path':f'logs/traces/{runner.task_id}.jsonl',
                'observer_errors':sorted(set(observer_errors)), 'reset':'own isolated profile per task/run'}
        finally:
            stop.set()
            if observer.is_alive():
                observer.join(5)
            timer.stop()
            window.close()
            if not controller._prompt_pool.waitForDone(15000):
                raise RuntimeError('Worker não encerrou; não iniciar outra tarefa.')
            session.close()
            window.deleteLater()
            controller.deleteLater()
            app.processEvents()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default='qwen3.5:4b')
    parser.add_argument('--profile',choices=['normal','conservative','game','focus'],default='normal')
    parser.add_argument('--runs',type=int,choices=range(1,4),default=3)
    parser.add_argument('--cases',nargs='+',type=int,choices=range(1,11),default=list(range(1,11)))
    parser.add_argument('--headless',action='store_true',help='Só diagnóstico; gate usa navegador visível.')
    parser.add_argument('--visible-ui',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Relatório existente; escolha outro destino.')
    environment = desktop_probe()
    if not environment['interactive_probe_passed']:
        parser.error('Sessão Windows/clipboard interativos indisponíveis; não simular.')
    from PyQt6.QtWidgets import QApplication
    from core.llm_client import OllamaClient
    from core.resource_profiles import resource_profile_scope
    from bench.reporting import summarize, markdown_report
    from bench.catalog import cases
    from PyQt6 import sip
    report = {'model':args.model,'profile':args.profile,'runs':args.runs,'rows':[],
        'scope':'Production HUD, real local model and browser; independent raw CDP/HTTP/filesystem oracle.',
        'environment':environment,'visible_browser':not args.headless,'milestone_complete':False,
        'runtime_fingerprint':runtime_fingerprint(ROOT),
        'limitations':['Local HTTP session test does not validate personal account login.',
                      'Media time advancement does not prove physical speaker output.',
                      'Raw traces and screenshot/profile data remain local and ignored.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    atomic_write(args.output,report)
    base = ROOT/'build/diagnostic'
    base.mkdir(parents=True,exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='browser-ui-',dir=base))
    with isolated_runtime() as host:
        client = OllamaClient(args.model,host=host,timeout=60)
        client.configure_thinking()
        from core.runtime_budget import InferencePressureError
        try:
            with resource_profile_scope(args.profile):
                client.converse('Bom dia, Nyx!')
        except InferencePressureError as exc:
            report['warmup'] = {'ok':False,'error_code':'RESOURCE_PRESSURE','error':str(exc)}
            report['rows'] = [{'id':f'browser-{number:02}','category':'browser','run':run,
                'ok':False,'status':'BLOCKED_ENVIRONMENT','false_success':False,'false_success_assessed':False,
                'elapsed_s':0,'actions':0,'error_code':'RESOURCE_PRESSURE','error':str(exc),
                'resources':{},'trace_path':None,'gate_eligible':False,'blocked_by_one_preflight':True}
                for run in range(1,args.runs+1) for number in args.cases]
            report['summary'] = summarize(report['rows'],args.runs)
            report['passed'] = False
            atomic_write(args.output,report)
            args.output.with_suffix('.md').write_text(markdown_report(report),encoding='utf-8')
            return 2
        app = QApplication([])
        try:
            for run in range(1,args.runs+1):
                for number in args.cases:
                    try:
                        row = trial(app,client,args.profile,base,number,run,args.headless,args.visible_ui)
                    except Exception as exc:
                        row = {'id':f'browser-{number:02}','category':'browser','run':run,'ok':False,'status':'ERROR',
                            'false_success':False,'false_success_assessed':False,'elapsed_s':0,
                            'error_code':type(exc).__name__,'error':str(exc).replace(str(base),'<WORK>').replace(str(ROOT),'<PROJECT>')[:500],
                            'resources':{},'trace_path':None}
                    import psutil
                    parent = psutil.Process()
                    before_gc = parent.memory_info().rss/1024**2
                    gc.collect()
                    app.processEvents()
                    after_gc = parent.memory_info().rss/1024**2
                    child_rss = {}
                    for member in parent.children(recursive=True):
                        try:
                            name = member.name()
                            child_rss[name] = round(child_rss.get(name,0)+member.memory_info().rss/1024**2,2)
                        except psutil.Error:
                            continue
                    row['reset_memory'] = {'harness_before_gc_mib':round(before_gc,2),
                        'harness_after_gc_mib':round(after_gc,2),'owned_children_rss_mib':child_rss}
                    report['rows'].append(row)
                    atomic_write(args.output,report)
                    print(row['id'],run,row['status'],row['error_code'],row['elapsed_s'],flush=True)
                    if row['false_success']:
                        raise RuntimeError('Falso sucesso crítico; corrigir antes de retomar novos efeitos.')
        finally:
            sip.delete(app)
    report['summary'] = summarize(report['rows'],args.runs)
    report['manifest'] = [case.to_dict() for case in cases() if case.id in {row['id'] for row in report['rows']}]
    report['passed'] = all(row['category_gate_passed'] for row in report['summary'].values())
    atomic_write(args.output,report)
    args.output.with_suffix('.md').write_text(markdown_report(report),encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
