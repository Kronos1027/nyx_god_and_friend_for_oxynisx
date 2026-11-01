"""Compare protocolo JSON e streaming em modelo real aquecido, sem ações de UI."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from audit.logger import AuditLogger  # noqa: E402
from cli import build_registry  # noqa: E402
from config import NyxConfig  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OllamaClient, parse_response  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.resource_profiles import resource_profile_scope, PROFILES  # noqa: E402
from core.task_runner import TaskRunner  # noqa: E402
from core.conversation import false_identity_claim  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--profile', choices=list(PROFILES), default='conservative')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--varied', action='store_true', help='Usa três cumprimentos/perguntas de identidade diferentes.')
    args = parser.parse_args()
    if not ensure_local_ollama().ready:
        raise RuntimeError('Ollama indisponível.')
    diagnostic = ROOT / 'build/diagnostic'
    diagnostic.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='conversation-bench-', dir=diagnostic))
    registry = build_registry(NyxConfig(allowed_roots=[base], log_dir=base / 'logs'))
    client = OllamaClient(model=args.model)
    client.configure_thinking()
    greeting = 'Bom dia, Nyx! Como você está?'
    inputs = [greeting, 'Boa noite, Nyx!', 'Quem é você?'] if args.varied else [greeting] * 3
    report = {'model': args.model, 'profile': args.profile, 'ui_used': False, 'inputs': inputs, 'rows': []}
    def no_tools(*args):
        raise RuntimeError('Nenhuma ferramenta pode executar no ensaio de conversa.')
    try:
        with resource_profile_scope(args.profile):
            started = time.monotonic()
            warmup = parse_response(client.generate(greeting, task_tools=[]))
            if not warmup.parse_ok:
                raise RuntimeError('Aquecimento não retornou JSON válido.')
            report['warmup_s'] = time.monotonic() - started
            for protocol in ('structured', 'stream'):
                for index in range(3):
                    greeting = inputs[index]
                    started = time.monotonic()
                    first, chunks = [], []
                    if protocol == 'structured':
                        response = parse_response(client.generate(greeting, task_tools=[]))
                    else:
                        loop = AgentLoop(client, registry, AuditLogger(base / 'logs', session_id=f'stream-{index}'))
                        runner = TaskRunner(loop)
                        runner._guard = no_tools
                        def progress(event, first=first, chunks=chunks, started=started):
                            if event['phase'] == 'conversation_delta':
                                if not first:
                                    first.append(time.monotonic() - started)
                                chunks.append(event['text'])
                        response = runner.start(greeting, progress).response
                    elapsed = time.monotonic() - started
                    text = response.speech_output
                    identity_issue = false_identity_claim(text)
                    report['rows'].append({'protocol': protocol, 'iteration': index + 1,
                        'input': greeting,
                        'elapsed_s': elapsed, 'first_delta_s': first[0] if first else None,
                        'passed': response.parse_ok and response.action.type == 'none' and bool(text)
                                  and (protocol != 'stream' or ''.join(chunks) == text)
                                  and not text.lstrip().startswith('{') and not identity_issue,
                        'known_false_identity_claim': identity_issue,
                        'response': text, 'generations': client.generation_report})
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(protocol, index + 1, round(elapsed, 3), first, flush=True)
        return 0 if all(row['passed'] for row in report['rows']) else 1
    except Exception as exc:
        report['error'] = str(exc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return 1
    finally:
        registry.browser_session.close()


if __name__ == '__main__':
    raise SystemExit(main())
