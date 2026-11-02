"""Measured M0 harness. Missing safe setups/verifiers are BLOCKED, never passes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from bench.catalog import cases, THRESHOLDS  # noqa: E402
from bench.environment import desktop_probe, ResourceSampler  # noqa: E402
from bench import verifiers  # noqa: E402
from bench.reporting import summarize, markdown_report  # noqa: E402
from bench.checkpoint import atomic_write, load_resume, runtime_fingerprint  # noqa: E402
from bench.native_suite import run_native_cases  # noqa: E402


def execute(case, run, client, profile, base):
    from audit.logger import AuditLogger
    from cli import build_registry
    from config import NyxConfig
    from core.agent_loop import AgentLoop
    from core.resource_profiles import resource_profile_scope
    from core.task_runner import TaskRunner

    work = base / f'{case.id}-{run}'
    work.mkdir()
    for index in range(1, 9):
        (work / f'numero-{index}.txt').write_text(str(index*11), encoding='utf-8')
    old_cwd = Path.cwd()
    registry = None
    os.chdir(work)
    chunks, first = [], []
    started = time.monotonic()
    def progress(event):
        if event.get('phase') == 'conversation_delta':
            if not first:
                first.append(time.monotonic()-started)
            chunks.append(event['text'])
    try:
        registry = build_registry(NyxConfig(allowed_roots=[work], log_dir=work / 'logs'))
        audit = AuditLogger(ROOT / 'logs', session_id='bench-' + uuid4().hex)
        loop = AgentLoop(client, registry, audit)
        runner = TaskRunner(loop)
        runner.set_budget_profile('default')
        runner.default_budget = (6, case.timeout_s)
        guard = runner._guard
        def fixture_only(tool, params):
            guard(tool, params)
            if case.route != 'file_sum' or tool not in {'read_file', 'find_files', 'calculator'}:
                raise ValueError('BLOCKED_POLICY: ensaio sem autorização para efeitos fora da fixture.')
        runner._guard = fixture_only
        with resource_profile_scope(profile):
            with ResourceSampler() as sampler:
                result = runner.start(case.prompt, progress)
                pending = result.needs_confirmation
                if pending:
                    # No approved UI harness exists for other capabilities yet.
                    result = runner.resume(runner.pending, False)
                speech = result.response.speech_output
                if case.route == 'file_sum':
                    verdict = verifiers.file_sum(work, speech)
                    reads = [s for s in runner.steps if s['tool']=='read_file' and s['ok'] and s['verified']]
                    names = {Path(s.get('resolved_path') or s['params'].get('path','')).name for s in reads}
                    calculations = [s for s in runner.steps if s['tool']=='calculator' and s['ok'] and s['verified']]
                    method_ok = len(reads)==8 and names=={f'numero-{i}.txt' for i in range(1,9)} and bool(calculations)
                    verdict['method_trace'] = {'read_actions':len(reads), 'distinct_files':len(names),
                                               'verified_calculations':len(calculations), 'ok':method_ok,
                                               'scope':'production action ledger; supplementary, not OS-level read auditing'}
                    verdict['objective_ok'] = verdict['ok']
                    verdict['ok'] = verdict['ok'] and method_ok
                else:
                    verdict = verifiers.conversation(speech, first[0] if first else None, chunks,
                                                     runner.steps, identity=case.route == 'identity')
        false_success = verdict.get('false_statement', False)
        trace = ROOT / 'logs/traces' / f'{runner.task_id}.jsonl'
        return {'ok': verdict['ok'] and not pending, 'status': 'PASS' if verdict['ok'] and not pending else 'FAIL',
                'false_success': bool(false_success), 'verifier': verdict, 'resources': sampler.report(),
                'error_code': None if verdict['ok'] else 'RESOURCE_PRESSURE' if runner.resource_pressure
                              else 'METHOD_MISSING' if verdict.get('objective_ok') else 'UNVERIFIED',
                'error': '' if verdict['ok'] else speech.replace(str(work), '<FIXTURE>'),
                'response': speech.replace(str(work), '<FIXTURE>'), 'actions': len(runner.steps),
                'trace_path': trace.relative_to(ROOT).as_posix() if trace.is_file() else None,
                'elapsed_s': round(time.monotonic()-started, 4)}
    finally:
        if registry is not None:
            registry.browser_session.close()
        os.chdir(old_cwd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, choices=range(3, 11), default=3)
    parser.add_argument('--categories', nargs='+', choices=['all', *THRESHOLDS], default=['all'])
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--profile', choices=['conservative', 'normal', 'game', 'focus'], default='conservative')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--list', action='store_true', help='Listar manifesto e cobertura, sem inferência.')
    parser.add_argument('--resume', action='store_true', help='Retomar relatório explicitamente, somente rotas de leitura/conversa.')
    args = parser.parse_args()
    selected = [case for case in cases() if 'all' in args.categories or case.category in args.categories]
    if args.list:
        print(json.dumps([case.to_dict() for case in selected], ensure_ascii=True, indent=2))
        return 0
    output = args.output or ROOT / 'docs/evidence' / f'bench_{datetime.now(timezone.utc):%Y-%m-%d}_M0.json'
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.resume:
        parser.error('O relatório já existe. Escolha outro --output ou use --resume para os casos seguros.')
    if args.resume and not output.is_file():
        parser.error('Não existe relatório para retomar.')
    artifacts = ROOT / 'build/diagnostic'
    artifacts.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='bench-', dir=artifacts))
    report = {'schema_version': 1, 'scope': 'production TaskRunner with independent verifiers; personal UI not operated',
              'model': args.model, 'profile': args.profile, 'runs': args.runs, 'milestone_complete': False,
              'environment': desktop_probe(), 'manifest': [case.to_dict() for case in selected], 'rows': [],
              'limitations': ['Safe routes currently cover conversation, numeric files and twelve native apps through an owned production Qt UI.',
                              'Blocked harness coverage is not proof that Nyx lacks the capability.',
                              'No M0-M8 milestone is completed by this partial runner alone.',
                              'GPU peaks are system samples, not exclusive Nyx allocation.']}
    fingerprint = runtime_fingerprint(ROOT)
    done = set()
    if args.resume:
        report, done = load_resume(output, selected, args.model, args.profile, args.runs, fingerprint)
        report.setdefault('resumptions', []).append({'completed_rows': len(done),
            'previous_inflight': report.get('inflight'), 'timestamp': datetime.now(timezone.utc).isoformat()})
    report.update(runtime_fingerprint=fingerprint, run_state='RUNNING', inflight=None)
    atomic_write(output, report)
    native = [case for case in selected if case.route=='native_app_ui'
              and any((case.id,run) not in done for run in range(1,args.runs+1))]
    if native:
        report['inflight'] = {'route':'native_app_ui','risk':'R1','cases':[case.id for case in native]}
        atomic_write(output,report)
        report['rows'].extend(run_native_cases(ROOT,native,args.runs,args.model,args.profile,base))
        done.update((row['id'],row['run']) for row in report['rows'])
        report['inflight'] = None
        atomic_write(output,report)
    client = None
    if any(case.route and case.route!='native_app_ui' and any((case.id, run) not in done for run in range(1,args.runs+1)) for case in selected):
        from core.llm_client import OllamaClient
        from core.ollama_service import ensure_local_ollama
        from core.resource_profiles import resource_profile_scope
        try:
            if not ensure_local_ollama().ready:
                raise RuntimeError('Runtime Ollama indisponível; nenhum substituto ativado.')
            client = OllamaClient(model=args.model)
            client.configure_thinking()
            started = time.monotonic()
            with resource_profile_scope(args.profile):
                client.converse('Bom dia, Nyx!')
            warmup = {'ok': True, 'elapsed_s': time.monotonic()-started}
        except Exception as exc:
            warmup = {'ok': False, 'error': str(exc)}
        if 'warmup' in report:
            report.setdefault('previous_warmups', []).append(report['warmup'])
        report['warmup'] = warmup
    for run in range(1, args.runs+1):
        for case in selected:
            if (case.id, run) in done:
                continue
            report['inflight'] = {'id': case.id, 'run': run, 'risk': case.risk, 'route': case.route}
            atomic_write(output, report)
            if not case.route:
                result = {'status': 'BLOCKED_HARNESS', 'ok': False, 'false_success': False,
                          'error_code': 'HARNESS_NOT_READY', 'error': 'Setup ou verificador independente seguro ainda não implementado.',
                          'elapsed_s': 0, 'trace_path': None}
            elif client is None:
                result = {'status': 'BLOCKED_RUNTIME', 'ok': False, 'false_success': False,
                          'error_code': 'RUNTIME_UNAVAILABLE', 'error': 'Modelo real indisponível.', 'elapsed_s': 0, 'trace_path': None}
            else:
                started = time.monotonic()
                try:
                    result = execute(case, run, client, args.profile, base)
                except Exception as exc:
                    result = {'status': 'ERROR', 'ok': False, 'false_success': False, 'error_code': type(exc).__name__,
                              'error': str(exc).replace(str(base), '<FIXTURE>'), 'elapsed_s': time.monotonic()-started, 'trace_path': None}
            resources = result.get('resources', {})
            report['rows'].append({'id': case.id, 'category': case.category, 'run': run, **result,
                'tempo_s': result['elapsed_s'], 'verificador': result.get('verifier'),
                'falso_sucesso': result['false_success'], 'erro_tipado': result['error_code'],
                'ram_pico_mib': resources.get('ram_peak_mib'), 'vram_pico_mib': resources.get('vram_peak_mib')})
            report['summary'] = summarize(report['rows'], args.runs) if len(report['rows']) == len(selected)*args.runs else None
            report['inflight'] = None
            atomic_write(output, report)
            print(case.id, run, result['status'], flush=True)
    report['summary'] = summarize(report['rows'], args.runs)
    report['passed'] = all(category['category_gate_passed'] for category in report['summary'].values())
    report['run_state'] = 'FINISHED'
    atomic_write(output, report)
    output.with_suffix('.md').write_text(markdown_report(report), encoding='utf-8')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
