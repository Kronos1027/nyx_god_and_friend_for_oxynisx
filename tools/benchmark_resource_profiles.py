"""Benchmark real e explícito; descarrega apenas o modelo escolhido entre perfis.

Não mede primeiro token: o protocolo atual é JSON sem streaming. Não executa
ações de desktop, não baixa pesos e não altera preferência persistente do modelo.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from core.llm_client import OllamaClient, parse_response  # noqa: E402
from core.ollama_service import ensure_local_ollama  # noqa: E402
from core.resource_profiles import resource_profile_scope, PROFILES  # noqa: E402
from core.runtime_budget import resource_snapshot, ollama_models  # noqa: E402


def unload(model):
    request = urllib.request.Request('http://127.0.0.1:11434/api/generate',
        data=json.dumps({'model': model, 'keep_alive': 0}).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read(65536)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--profile', action='append', choices=list(PROFILES))
    parser.add_argument('--repeat', type=int, choices=range(1, 4), default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    state = ensure_local_ollama()
    if not state.ready:
        raise RuntimeError(state.reason)
    if not any(m.get('name') == args.model for m in ollama_models('http://127.0.0.1:11434', 'tags')):
        raise RuntimeError('Modelo não instalado; nenhum download foi iniciado.')
    report = {'model': args.model, 'ui_used': False, 'streaming': False, 'rows': []}
    for profile in args.profile or ['conservative', 'normal']:
        unload(args.model)
        with resource_profile_scope(profile):
            client = OllamaClient(model=args.model)
            client.configure_thinking()
            for index in range(args.repeat):
                stop = threading.Event()
                samples = [resource_snapshot()]
                def sample(stop=stop, samples=samples):
                    while not stop.wait(.25):
                        samples.append(resource_snapshot())
                thread = threading.Thread(target=sample, daemon=True)
                thread.start()
                row = {'profile': profile, 'iteration': index + 1, 'resources_before': asdict(samples[0])}
                started = time.perf_counter()
                try:
                    parsed = parse_response(client.generate('Bom dia, Nyx! Como você está? Responda brevemente em português.', task_tools=[]))
                    row.update(passed=parsed.parse_ok and parsed.action.type == 'none' and bool(parsed.speech_output),
                               response=parsed.speech_output, generations=client.generation_report,
                               resident=ollama_models(client.host, 'ps'))
                except Exception as exc:
                    row.update(passed=False, error=str(exc))
                finally:
                    row['elapsed_s'] = round(time.perf_counter() - started, 3)
                    stop.set()
                    thread.join(timeout=2)
                    samples.append(resource_snapshot())
                    row['ram_min_free_bytes'] = min((s.ram_available_bytes for s in samples if s.ram_available_bytes is not None), default=None)
                    row['gpu_peak_used_bytes_system'] = max((s.vram_total_bytes - s.vram_free_bytes for s in samples
                        if s.vram_total_bytes is not None and s.vram_free_bytes is not None), default=None)
                    row['sample_count'] = len(samples)
                report['rows'].append(row)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps({k: row[k] for k in ('profile', 'iteration', 'passed', 'elapsed_s')}, ensure_ascii=False), flush=True)
    unload(args.model)


if __name__ == '__main__':
    main()
