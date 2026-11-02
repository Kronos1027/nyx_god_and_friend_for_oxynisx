"""Qualify installed fallback conversation models on an explicitly isolated runtime.

Inventory is read-only. Inference requires --run and a non-personal loopback
endpoint. This script never starts/stops a runtime, downloads weights, executes
tools or unloads anyone's model. The caller owns runtime lifecycle.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time
from urllib.parse import urlsplit
import urllib.request

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'src'))
from bench.fallback_cases import CASES, evaluate  # noqa: E402
from core.conversation import false_identity_claim  # noqa: E402
from core.llm_client import OllamaClient, parse_response  # noqa: E402
from core.model_prompts import FALLBACK_CONVERSATION_PROMPTS, conversation_prompt_for_model  # noqa: E402
from core.personality import NYX_CONVERSATION_PROMPT  # noqa: E402
from core.resource_profiles import resource_profile_scope  # noqa: E402
from core.runtime_budget import resource_snapshot  # noqa: E402

CANDIDATES=tuple(FALLBACK_CONVERSATION_PROMPTS)


def endpoint(value, *, inference=False):
    parsed=urlsplit(value)
    if (parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost'}
            or parsed.username or parsed.password or parsed.path not in {'','/'}
            or parsed.query or parsed.fragment):
        raise ValueError('Use somente um endpoint HTTP loopback sem caminho ou credenciais.')
    port=parsed.port or 80
    if inference and port in {80,11434}:
        raise ValueError('A inferência exige porta isolada diferente da instância pessoal11434.')
    return f'http://127.0.0.1:{port}'


def read_api(host,name):
    with urllib.request.urlopen(host+'/api/'+name,timeout=5) as response:
        data=response.read(2_097_153)
    if len(data)>2_097_152:
        raise ValueError('Resposta de inventário excessiva.')
    return json.loads(data)


class ProcessSampler:
    """Read only working sets of the supplied runtime and validated descendants."""
    def __init__(self,server_pid=None):
        self.parent=psutil.Process(server_pid) if server_pid else None
        self.created=self.parent.create_time() if self.parent else None
        self.known={}

    def sample(self):
        ram=psutil.virtual_memory()
        gpu=resource_snapshot()
        result={'host_available_bytes':ram.available,'host_used_bytes':ram.used,
                'runtime_rss_bytes':None,'runtime_private_bytes':None,
                'system_vram_used_bytes':gpu.vram_total_bytes-gpu.vram_free_bytes
                    if gpu.vram_total_bytes is not None and gpu.vram_free_bytes is not None else None}
        if self.parent and self.parent.create_time()==self.created:
            self.known[self.parent.pid]=self.created
            for item in self.parent.children(recursive=True):
                try:
                    created=item.create_time()
                    if created>=self.created:
                        self.known[item.pid]=created
                except psutil.Error:
                    continue
            rss=private=0
            for pid,created in list(self.known.items()):
                try:
                    item=psutil.Process(pid)
                    if item.create_time()!=created:
                        continue
                    memory=item.memory_info()
                    rss+=memory.rss
                    private+=getattr(memory,'private',0)
                except psutil.Error:
                    continue
            result.update(runtime_rss_bytes=rss,runtime_private_bytes=private)
        return result


def summarize(rows,models,runs,variants):
    result=[]
    for model in models:
        for variant in variants:
            selected=[r for r in rows if r['model']==model and r['prompt_variant']==variant]
            categories={}
            for name in ('fact','abstention','conversation','identity'):
                subset=[r for r in selected if r['category']==name]
                categories[name]={'passed':sum(bool(r['evaluation']['ok']) for r in subset),
                                  'total':len(subset),'outcomes':dict(Counter(r['evaluation']['outcome'] for r in subset))}
            first=[r['first_delta_seconds'] for r in selected if r['first_delta_seconds'] is not None]
            result.append({'model':model,'prompt_variant':variant,'categories':categories,
                'rows':len(selected),'expected_rows':len(CASES)*runs,
                'complete':len(selected)==len(CASES)*runs,
                'median_first_delta_seconds':statistics.median(first) if first else None,
                'false_identity_count':sum(bool(r['evaluation']['false_identity']) for r in selected),
                'inappropriate_action_claims':sum(bool(r['evaluation']['inappropriate_action_claim']) for r in selected),
                'delivery_failures':sum(not r['evaluation']['stream_delivery'] for r in selected)})
    # Report only complete candidates. Accuracy and uncertainty are separate;
    # speed is a tie breaker and cannot compensate for an incorrect answer.
    def rank(item):
        cats=item['categories']
        return (cats['fact']['passed']/max(1,cats['fact']['total']),
                cats['abstention']['passed']/max(1,cats['abstention']['total']),
                -item['false_identity_count'],-item['inappropriate_action_claims'],
                -item['delivery_failures'],-(item['median_first_delta_seconds'] or float('inf')))
    complete=[item for item in result if item['complete'] and item['prompt_variant']=='tailored']
    best=max(complete,key=rank) if len(complete)==len(models) else None
    return {'candidates':result,'best_observed_tailored_model':best['model'] if best else None,
            'selection_is_automatic':False,'general_quality_certified':False,
            'selection_scope':'Only this small synthetic corpus; every extra factual claim requires human review.'}


def save_report(path,report):
    # First creation is exclusive. Later atomic replacements only update this
    # execution's file; main rejected an existing destination before inference.
    temporary=path.with_name(path.name+'.writing')
    with temporary.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary,path)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='http://127.0.0.1:11434')
    parser.add_argument('--models',nargs='+',choices=CANDIDATES,default=list(CANDIDATES))
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--prompt-variants',nargs='+',choices=('tailored','shared'),default=['tailored'])
    parser.add_argument('--server-pid',type=int,help='PID do servidor próprio, somente para medir RSS; nenhum PID é encerrado.')
    parser.add_argument('--run',action='store_true',help='Executa inferência real; sem esta opção, só inventário read-only.')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if not 1<=args.runs<=3:
        parser.error('Use uma a três rodadas; qualificação completa exige três.')
    try:
        host=endpoint(args.host,inference=args.run)
    except ValueError as exc:
        parser.error(str(exc))
    if args.output.exists() or args.output.with_name(args.output.name+'.writing').exists():
        parser.error('Escolha uma evidência nova; resultados anteriores não serão sobrescritos.')
    inventory=read_api(host,'tags').get('models',[])
    installed={item.get('name'):item for item in inventory}
    missing=[model for model in args.models if model not in installed]
    if missing:
        parser.error('Candidato não instalado; nenhum download será realizado: '+', '.join(missing))
    version=read_api(host,'version').get('version')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report={'schema_version':1,'kind':'fallback_conversation_qualification',
        'inference_performed':args.run,'ui_used':False,'tools_executed':False,
        'runtime_lifecycle_managed_here':False,'runtime_version':version,
        'profile':'conservative','context_tokens_expected':4096,'runs':args.runs,
        'model_inventory':[{k:installed[model].get(k) for k in ('name','size','digest','details')} for model in args.models],
        'corpus':[asdict(case) for case in CASES],
        'gold_is_sent_to_model':False,
        'prompt_candidates':{model:conversation_prompt_for_model(model) for model in args.models},
        'shared_prompt':NYX_CONVERSATION_PROMPT if 'shared' in args.prompt_variants else None,
        'rows':[],
        'limitations':['Real production converse streaming, without HUD, tools, personal memory or sensors.',
            'Fact checks are narrow exact-answer predicates, not proof that all extra claims are true.',
            'Conversational case checks delivery only; warmth and usefulness need human review.',
            'Portuguese abstention heuristics can miss paraphrases; full synthetic answers retained for review.',
            'Host memory includes other programs; runtime RSS sums working sets and may double-count shared pages.',
            'File cache is not reset. First case per model includes cold load if runtime was empty.',
            'Ranking does not change production preferences or certify general quality.']}
    if not args.run:
        report['summary']={'status':'inventory_only_no_inference_no_model_selection'}
        save_report(args.output,report)
        print(json.dumps(report['summary']))
        return 0
    sampler=ProcessSampler(args.server_pid)
    for model in args.models:
        client=OllamaClient(model=model,host=host,timeout=60)
        client.configure_thinking()
        for run in range(1,args.runs+1):
            for variant in args.prompt_variants:
                client.conversation_system_prompt=conversation_prompt_for_model(model) if variant=='tailored' else NYX_CONVERSATION_PROMPT
                for case in CASES:
                    started=time.monotonic()
                    samples=[sampler.sample()]
                    stop=threading.Event()
                    def poll(samples=samples,stop=stop):
                        while not stop.wait(.1):
                            try:
                                samples.append(sampler.sample())
                            except psutil.Error:
                                continue
                    worker=threading.Thread(target=poll,daemon=True)
                    worker.start()
                    deltas=[]
                    first=[]
                    text=''
                    error=None
                    complete=False
                    try:
                        def delta(value,first=first,deltas=deltas,started=started):
                            if not first:
                                first.append(time.monotonic()-started)
                            deltas.append(value)
                        with resource_profile_scope('conservative'):
                            response=parse_response(client.converse(case.question,on_delta=delta))
                        text=response.speech_output
                        complete=response.parse_ok
                    except Exception as exc:
                        error=type(exc).__name__  # No local paths or server logs in public evidence.
                    finally:
                        stop.set()
                        worker.join(2)
                    samples.append(sampler.sample())
                    rss=[s['runtime_rss_bytes'] for s in samples if s['runtime_rss_bytes'] is not None]
                    vram=[s['system_vram_used_bytes'] for s in samples if s['system_vram_used_bytes'] is not None]
                    row={'model':model,'prompt_variant':variant,'run':run,'id':case.id,'category':case.category,
                        'response':text,'error_type':error,'first_delta_seconds':first[0] if first else None,
                        'elapsed_seconds':time.monotonic()-started,
                        'resource_samples':len(samples),'peak_runtime_rss_bytes':max(rss) if rss else None,
                        'peak_system_vram_used_bytes':max(vram) if vram else None,
                        'system_vram_scope':'All GPU processes, not exclusive model allocation.',
                        'minimum_host_available_bytes':min(s['host_available_bytes'] for s in samples),
                        'host_available_before_bytes':samples[0]['host_available_bytes'],
                        'generation_report':client.generation_report,
                        'evaluation':evaluate(case,text,streamed=bool(deltas and ''.join(deltas)==text),
                                              complete=complete,false_identity=false_identity_claim(text))}
                    report['rows'].append(row)
                    report['summary']=summarize(report['rows'],args.models,args.runs,args.prompt_variants)
                    save_report(args.output,report)
                    print(json.dumps({k:row[k] for k in ('model','prompt_variant','run','id','error_type','evaluation')},ensure_ascii=True),flush=True)
                    if error:
                        # Resource pressure or transport error is not model
                        # factual failure. Preserve evidence and stop this run.
                        report['stopped_after_runtime_error']=error
                        save_report(args.output,report)
                        return 1
    report['resources_at_end']=asdict(resource_snapshot())
    report['complete']=len(report['rows'])==len(args.models)*args.runs*len(args.prompt_variants)*len(CASES)
    save_report(args.output,report)
    return 0 if report['complete'] else 1


if __name__=='__main__':
    raise SystemExit(main())
