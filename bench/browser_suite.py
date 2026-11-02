"""Execute all browser acceptance tasks in an owned production Qt process."""
import json
from pathlib import Path
import subprocess
import sys


def run_browser_cases(root, selected, runs, model, profile, artifacts):
    targets = [case for case in selected if case.route=='browser_ui']
    report = Path(artifacts)/'browser-ui.json'
    log = Path(artifacts)/'browser-ui.log'
    command = [sys.executable,str(root/'tools/verify_browser_ui.py'),'--runs',str(runs),
        '--model',model,'--profile',profile,'--output',str(report),
        '--cases',*[str(int(case.id.split('-')[1])) for case in targets]]
    try:
        with log.open('w',encoding='utf-8') as output:
            result = subprocess.run(command,cwd=root,stdout=output,stderr=subprocess.STDOUT,
                timeout=len(targets)*runs*220+180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            code = result.returncode
    except subprocess.TimeoutExpired:
        code = 'TIMEOUT'
    data = json.loads(report.read_text(encoding='utf-8')) if report.is_file() else {'rows':[]}
    rows = []
    for case in targets:
        for run in range(1,runs+1):
            observed = next((row for row in data['rows'] if row['id']==case.id and row['run']==run),None)
            if observed is None:
                observed = {'ok':False,'status':'ERROR','false_success':False,'elapsed_s':0,
                    'error_code':'BROWSER_UI_'+str(code),'error':'Execução não concluída; confira o log local antes de repetir efeitos.',
                    'resources':{},'trace_path':None}
            resources = observed.get('resources',{})
            rows.append({'id':case.id,'category':'browser','run':run,**observed,
                'gate_eligible':observed.get('gate_eligible',True),'tempo_s':observed['elapsed_s'],'verificador':observed.get('verifier'),
                'falso_sucesso':observed['false_success'],'erro_tipado':observed.get('error_code'),
                'ram_pico_mib':resources.get('ram_peak_mib'),'vram_pico_mib':resources.get('vram_peak_mib')})
    return rows
