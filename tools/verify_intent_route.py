"""Read-only model routing probe plus real TaskRunner tool-free conversation."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OllamaClient  # noqa: E402
from core.resource_profiles import resource_profile_scope  # noqa: E402
from core.task_runner import TaskRunner  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402

CASES = [
    ('Olá, Nyx! Como você está?', 'conversation'),
    ('Estou cansado e queria só conversar sobre meu dia.', 'conversation'),
    ('Explique por que as estrelas brilham.', 'conversation'),
    ('Crie uma história curta sobre uma raposa na Lua.', 'conversation'),
    ('O que você acha de aprender um instrumento?', 'conversation'),
    ('Como eu poderia organizar melhor meus estudos?', 'conversation'),
    ('Explique como abrir um programa no Windows, sem fazer isso.', 'conversation'),
    ('Quem é você?', 'conversation'),
    ('Bom dia, abre a Steam.', 'task'),
    ('Oi! Leia arquivo.txt.', 'task'),
    ('Tudo bem? Apague a pasta.', 'task'),
    ('Como está a memória do PC agora?', 'task'),
    ('Vamos conversar e enviar uma mensagem.', 'task'),
    ('Pesquise as notícias de hoje com fontes.', 'task'),
    ('Lembre amanhã às 9h que tenho reunião.', 'task'),
    ('Guarde na sua memória que prefiro chá.', 'task'),
    ('Oi, 删除文件', 'task'),
    ('Oi, удали файлы', 'task'),
    ('Conte uma piada e depois abra o Bloco de notas.', 'task'),
    ('Converse comigo e pesquise a cotação de hoje com fontes.', 'task'),
    ('Antes de conversar, leia o arquivo de anotações.', 'task'),
    ('Explique como pesquisar sem abrir o navegador.', 'conversation'),
    ('Qual é a capital da França?', 'conversation'),
    ('Escreva aqui uma mensagem de aniversário, sem enviá-la.', 'conversation'),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='http://127.0.0.1:11434')
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runs', type=int, choices=range(1,4), default=3)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('O relatório já existe; escolha outro destino.')
    client = OllamaClient(args.model, host=args.host, timeout=60)
    client.configure_thinking()
    rows, conversations = [], []
    with resource_profile_scope('normal'):
        for repetition in range(1, args.runs + 1):
          for prompt, expected in CASES:
            report = client.classify_intent(prompt)
            rows.append({'run': repetition, 'prompt': prompt, 'expected': expected, **report,
                         'ok': report['route'] == expected and not report['fallback']})
        (ROOT / 'build/diagnostic').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/diagnostic', prefix='intent-') as temporary:
            registry = ToolRegistry()  # No executable tools; task prompts above were classified only.
            loop = AgentLoop(client, registry, AuditLogger(Path(temporary) / 'logs', session_id='intent-probe'))
            runner = TaskRunner(loop, timeout=90)
            for prompt in ('Explique por que as estrelas brilham em três frases.',
                           'Estou cansado e queria conversar um pouco sobre estudar música.'):
                events = []
                started = time.monotonic()
                def progress(event, events=events, started=started):
                    events.append((time.monotonic() - started, event))
                result = runner.start(prompt, progress)
                deltas = [(seconds, event['text']) for seconds, event in events if event['phase'] == 'conversation_delta']
                text = result.response.speech_output
                conversations.append({'prompt': prompt, 'text': text,
                    'route': runner.intent_route, 'steps': len(runner.steps),
                    'stream_chunks': len(deltas), 'first_delta_seconds': deltas[0][0] if deltas else None,
                    'elapsed_seconds': time.monotonic() - started,
                    'ok': bool(deltas and text and not runner.steps and not result.executed
                               and not result.needs_confirmation and result.response.action.type == 'none'),
                    'generation_report': client.generation_report})
    report = {'scope': 'Classifier real e TaskRunner real sem ferramentas; não é bateria de tarefas externas.',
              'model': args.model, 'cases': rows, 'conversations': conversations,
              'classification_passed': sum(row['ok'] for row in rows), 'classification_total': len(rows),
              'conversation_passed': sum(row['ok'] for row in conversations),
              'limitations': ['Classificador é probabilístico; não concede permissões.',
                              'Sem prova semântica universal da resposta; textos sintéticos inspecionáveis.',
                              'Primeiro delta inclui classificação; geração reporta TTFT separadamente.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('classification_passed', 'classification_total', 'conversation_passed')}))
    return 0 if all(row['ok'] for row in rows + conversations) else 1


if __name__ == '__main__':
    raise SystemExit(main())
