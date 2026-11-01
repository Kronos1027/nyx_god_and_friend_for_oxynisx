"""Compare modelos locais em três tarefas reais, sem desktop ou respostas simuladas.

Descarrega os modelos escolhidos entre fases para evitar comparar um modelo
bloqueado por outro ainda residente. Não muda preferência nem baixa modelos.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from benchmark_resource_profiles import unload  # noqa: E402
from verify_context_workflow import run_workflow  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.resource_profiles import resource_profile_scope, PROFILES  # noqa: E402
from core.runtime_budget import ollama_models  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='append', required=True)
    parser.add_argument('--profile', choices=list(PROFILES), default='normal')
    parser.add_argument('--repeat', type=int, choices=range(1, 4), default=3)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = ensure_local_ollama()
    if not state.ready:
        raise RuntimeError(state.reason)
    installed = {m['name'] for m in ollama_models('http://127.0.0.1:11434', 'tags')}
    if not set(args.model) <= installed:
        raise ValueError('Modelo não instalado. Nenhum download foi iniciado.')
    summary = {'profile': args.profile, 'direct_method_requested': True, 'results': []}
    for model in args.model:
        unload(model)
    for index, model in enumerate(args.model):
        for repeat in range(args.repeat):
            file = output / f'model-{index + 1}-run-{repeat + 1}.json'
            with resource_profile_scope(args.profile):
                run_workflow(model, file, direct=True)
            result = json.loads(file.read_text(encoding='utf-8'))
            summary['results'].append({'model': model, 'iteration': repeat + 1,
                'passed': result['passed'], 'elapsed_s': result['elapsed_seconds'],
                'actions': result['actions'], 'verified_reads': result['verified_reads'],
                'goal_delivered': result.get('goal_delivered'), 'redundant_reads': result.get('redundant_reads')})
            (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        unload(model)
    return 0 if summary['results'] and all(row['passed'] for row in summary['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
