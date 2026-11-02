"""Run the owned production-UI harness in its own Qt process, sequentially."""
import json
from pathlib import Path
import subprocess
import sys
from bench.catalog import NATIVE_CASES
from bench.app_inventory import precheck_running


def run_native_cases(root, selected, runs, model, profile, artifacts):
    targets = [case for case in selected if case.route=='native_app_ui']
    if not targets:
        return []
    def target(case):
        return case.target or NATIVE_CASES[case.id]
    blocked = {row['app']:row for row in precheck_running([target(case) for case in targets])}
    ready = [case for case in targets if target(case) not in blocked]
    report_path = Path(artifacts)/'native-ui.json'
    log_path = Path(artifacts)/'native-ui.log'
    command = [sys.executable,str(root/'tools/verify_native_app_ui.py'),'--visible-ui','--runs',str(runs),
               '--model',model,'--profile',profile,'--output',str(report_path),
               '--apps',*[target(case) for case in ready]]
    exit_code = None
    if not ready:
        exit_code = 'PRECHECK_CLOSE_APP'
    else:
        try:
            with log_path.open('w',encoding='utf-8') as log:
                completed = subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,
                    timeout=len(ready)*runs*155+180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            exit_code = 'TIMEOUT'
    data = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {'rows':[]}
    rows = []
    for case in targets:
        for run in range(1,runs+1):
            observed = next((row for row in data['rows'] if row['app']==target(case) and row['run']==run),None)
            if target(case) in blocked:
                row = {'status':'BLOCKED_ENVIRONMENT','ok':False,'false_success':False,
                       'error_code':'PRECHECK_CLOSE_APP','error':blocked[target(case)]['message'],
                       'elapsed_s':0,'trace_path':None,'resources':{}}
            elif observed is None:
                failure = data.get('runtime_failure', {})
                row = {'status':'BLOCKED_RUNTIME','ok':False,'false_success':False,
                       'error_code':failure.get('error_code', 'NATIVE_UI_HARNESS_'+str(exit_code)),
                       'error':failure.get('error', 'Execução Qt incompleta; diagnóstico local preservado.'),
                       'elapsed_s':0,'trace_path':None,'resources':{}}
            else:
                row = {**observed,'status':observed.get('status','PASS' if observed['ok'] else 'FAIL'),
                       'error':'' if observed['ok'] else 'Verificação independente ou fluxo da UI não concluiu; confira o trace local.'}
            resources = row.get('resources',{})
            rows.append({'id':case.id,'category':case.category,'run':run,**row,
                         'gate_eligible':bool(row.get('cold_start_prechecked')),
                         'gate_limitation':'Só abertura com pré-checagem fria é elegível; foco é métrica separada.',
                         'tempo_s':row['elapsed_s'],'verificador':row.get('verifier'),
                         'falso_sucesso':row['false_success'],'erro_tipado':row['error_code'],
                         'ram_pico_mib':resources.get('ram_peak_mib'),'vram_pico_mib':resources.get('vram_peak_mib')})
    return rows
