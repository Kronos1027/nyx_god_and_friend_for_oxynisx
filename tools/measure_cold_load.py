"""Measure existing local weights on an owned, isolated Ollama server; never download."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from core.ollama_service import load_runtime_config  # noqa: E402
from core.resource_profiles import resource_profile_scope  # noqa: E402
from core.runtime_budget import resource_snapshot, post_ollama_json  # noqa: E402


def request(host, endpoint, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(host + '/api/' + endpoint, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read(2_097_153))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--automatic', action='store_true', help='Escolha real do perfil/modelo pelos recursos atuais e preferência salva.')
    parser.add_argument('--profile', choices=['normal','conservative','game','focus'], default='normal')
    parser.add_argument('--port', type=int, default=11435)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--intent-output', type=Path)
    parser.add_argument('--hud-output', type=Path)
    parser.add_argument('--native-output', type=Path, help='Ensaio HUD Calculadora; não fecha o app aberto.')
    args = parser.parse_args()
    if any(path and path.exists() for path in (args.output,args.intent_output,args.hud_output,args.native_output)):
        parser.error('Escolha relatórios novos; evidências anteriores não serão sobrescritas.')
    if not 1024 <= args.port <= 65535 or not 1 <= args.runs <= 3:
        parser.error('Porta/rodadas fora do limite.')
    config = load_runtime_config()
    executable, models = Path(config['ollama_executable']), Path(config['models_directory'])
    if not executable.is_file() or not models.is_dir():
        parser.error('Configure uma instalação e pesos locais existentes; este probe não instala nada.')
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', args.port))
    host = f'http://127.0.0.1:{args.port}'
    private = ROOT / 'build/diagnostic/cold-load'
    private.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, 'OLLAMA_HOST': f'127.0.0.1:{args.port}',
        'NYX_OLLAMA_HOST': host,
        'OLLAMA_MODELS': str(models), 'OLLAMA_MAX_LOADED_MODELS': '1',
        'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_NO_CLOUD': '1',
        'OLLAMA_TMPDIR': str(private), 'TEMP': str(private), 'TMP': str(private)}
    owned, rows, intent_code, selection = {}, [], None, None
    hud_code = native_code = None
    with (private / 'server.log').open('ab') as output:
        process = subprocess.Popen([str(executable), 'serve'], env=environment,
            stdin=subprocess.DEVNULL, stdout=output, stderr=output,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    parent = psutil.Process(process.pid)
    owned[parent.pid] = parent.create_time()
    def sample():
        result = {'rss': 0, 'private': 0}
        for item in [parent, *parent.children(recursive=True)]:
            try:
                created = item.create_time()
                if created < owned[parent.pid]:
                    continue
                owned[item.pid] = created
                memory = item.memory_info()
                result['rss'] += memory.rss
                result['private'] += getattr(memory, 'private', 0)
            except psutil.Error:
                continue
        result['ram_available'] = psutil.virtual_memory().available
        return result
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                request(host, 'version')
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Servidor próprio não iniciou; consulte log privado.') from None
                time.sleep(.15)
        if args.automatic:
            from core.resource_profiles import default_profile
            from core.llm_client import create_llm_client
            snapshot = resource_snapshot()
            args.profile, reason = default_profile(snapshot)
            previous_host = os.environ.get('NYX_OLLAMA_HOST')
            os.environ['NYX_OLLAMA_HOST'] = host
            try:
                with resource_profile_scope(args.profile):
                    client, backend = create_llm_client()
                args.model = getattr(client, 'model', '')
                selection = {'profile': args.profile, 'reason': reason, 'backend':backend,
                             'model':args.model, 'notice':getattr(client,'runtime_notice',''),
                             'resources':asdict(snapshot)}
            finally:
                if previous_host is None:
                    os.environ.pop('NYX_OLLAMA_HOST', None)
                else:
                    os.environ['NYX_OLLAMA_HOST'] = previous_host
        inventory = request(host, 'tags').get('models', [])
        installed = next((item for item in inventory if item.get('name') == args.model), None)
        if not installed:
            raise RuntimeError('Modelo não instalado; nenhum download executado.')
        for run in range(1, args.runs + 1):
            request(host, 'generate', {'model': args.model, 'keep_alive': 0})
            if request(host, 'ps').get('models'):
                raise RuntimeError('Unload não confirmado; não chamar a próxima carga de fria.')
            before, samples, stop = asdict(resource_snapshot()), [], threading.Event()
            baseline = sample()
            def poll(stop=stop, samples=samples):
                while not stop.wait(.1):
                    samples.append(sample())
            worker = threading.Thread(target=poll, daemon=True)
            worker.start()
            started, error, response = time.monotonic(), None, {}
            try:
                with resource_profile_scope(args.profile):
                    response = post_ollama_json(host + '/api/chat', {'model': args.model,
                        'messages': [{'role':'user', 'content':'Responda oi.'}], 'think': False,
                        'stream':False, 'options': {'num_predict':1}}, 90)
            except Exception as exc:
                error = type(exc).__name__ + ': ' + str(exc)
            finally:
                stop.set()
                worker.join(2)
            samples.append(sample())
            running = request(host, 'ps').get('models', [])
            rows.append({'run':run, 'cold_runner':True, 'os_file_cache_reset':False,
                'ok': bool(response.get('done') and running and not error), 'error':error,
                'elapsed_seconds': time.monotonic() - started, 'before':before,
                'baseline_owned_rss_bytes':baseline['rss'],
                'peak_owned_rss_bytes':max(s['rss'] for s in samples),
                'peak_owned_private_bytes':max(s['private'] for s in samples),
                'minimum_system_available_bytes':min(s['ram_available'] for s in samples),
                'resident': [{k:v for k,v in item.items() if k in {'name','size','size_vram','context_length'}} for item in running],
                'load_duration_ns':response.get('load_duration')})
            if error:
                break
        if args.intent_output:
            intent_code = subprocess.run([sys.executable, str(ROOT/'tools/verify_intent_route.py'),
                '--host',host,'--model',args.model,'--output',str(args.intent_output)],
                env=environment, timeout=300, check=False).returncode
        if args.hud_output:
            hud_code = subprocess.run([sys.executable, str(ROOT/'tools/verify_conversation_ui.py'),
                '--host',host,'--profile',args.profile,'--model',args.model,
                *(['--automatic-model'] if args.automatic else []),
                '--prompt','Explique por que as estrelas brilham.',
                '--output',str(args.hud_output)],env=environment,timeout=180,check=False).returncode
        if args.native_output:
            native_code = subprocess.run([sys.executable, str(ROOT/'tools/verify_native_app_ui.py'),
                '--apps','calculator','--runs','3','--profile',args.profile,'--model',args.model,
                '--output',str(args.native_output)],env=environment,timeout=240,check=False).returncode
    finally:
        # Only descendants observed beneath our Popen, revalidated by creation.
        try:
            sample()
        except psutil.Error:
            pass
        for pid, created in reversed(list(owned.items())):
            try:
                item = psutil.Process(pid)
                if item.create_time() == created:
                    item.terminate()
            except psutil.Error:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if psutil.Process(process.pid).create_time() == owned[parent.pid]:
                process.kill()
    report = {'model':args.model, 'profile':args.profile, 'automatic_selection':selection,
        'runs':rows, 'intent_probe_exit_code':intent_code,
        'hud_probe_exit_code':hud_code, 'native_probe_exit_code':native_code,
        'scope':'Servidor Ollama e filhos próprios, pesos existentes; sem apps pessoais.',
        'limitations':['RAM total do sistema sofre interferência de outros processos.',
            'RSS soma working sets e pode duplicar páginas compartilhadas; amostragem 100ms.',
            'Carga fria do runner; cache de arquivos do Windows não foi esvaziado.',
            'Mínimo inicial observado não prova limite mínimo necessário: sem stress artificial de RAM.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'runs':len(rows),'passed':sum(row['ok'] for row in rows),'intent_code':intent_code}))
    return 0 if (len(rows)==args.runs and all(row['ok'] for row in rows)
                 and all(code in {None,0} for code in (intent_code,hud_code,native_code))) else 1


if __name__ == '__main__':
    raise SystemExit(main())
