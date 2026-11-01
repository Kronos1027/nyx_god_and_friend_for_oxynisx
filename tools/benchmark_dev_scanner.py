"""Measure the isolated development scanner; never scans or prints credentials."""
import json
from pathlib import Path
import subprocess
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    environment = ROOT/'.local-deps/security-env'
    rows = []
    try:
        import pynvml
        pynvml.nvmlInit()
        gpu = pynvml, pynvml.nvmlDeviceGetHandleByIndex(0)
    except Exception:
        gpu = None
    try:
        for iteration in range(1,7):
            tool = 'detect-secrets' if iteration <= 3 else 'pre-commit'
            executable = environment/f'Scripts/{tool}.exe'
            started = time.perf_counter()
            process = subprocess.Popen([str(executable),'--version'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            rss, gpu_seen, gpu_known = 0, False, gpu is not None
            probe = psutil.Process(process.pid)
            while process.poll() is None:
                pids = {process.pid}
                try:
                    members = [probe,*probe.children(recursive=True)]
                    memory = 0
                    for member in members:
                        try:
                            memory += member.memory_info().rss
                            pids.add(member.pid)
                        except psutil.Error:
                            pass
                    rss = max(rss,memory)
                except psutil.Error:
                    pass
                if gpu_known:
                    try:
                        api,handle = gpu
                        active = [*api.nvmlDeviceGetComputeRunningProcesses(handle),*api.nvmlDeviceGetGraphicsRunningProcesses(handle)]
                        gpu_seen = gpu_seen or any(p.pid in pids for p in active)
                    except Exception:
                        gpu_known = False
                time.sleep(.005)
            stdout,stderr = process.communicate()
            rows.append({'tool':tool,'run':(iteration-1)%3+1,'startup_s':round(time.perf_counter()-started,4),
                         'peak_rss_mib':round(rss/1024**2,2),'gpu_process_query_available':gpu_known,
                         'scanner_gpu_process_observed':gpu_seen if gpu_known else None,
                         'exit_code':process.returncode,'version':stdout.decode().strip() if process.returncode==0 else None})
        query = "import importlib.metadata as m,json;print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()}))"
        versions = json.loads(subprocess.check_output([str(environment/'Scripts/python.exe'),'-c',query],cwd=ROOT))
        installed_bytes = sum(path.stat().st_size for path in environment.rglob('*') if path.is_file())
        report = {'purpose':'development-only isolated environment on project volume; not imported by Nyx',
                  'detect_secrets_wheel_bytes':120341,'pre_commit_wheel_bytes':226261,
                  'installed_environment_bytes':installed_bytes,
                  'versions':versions,'rows':rows,'sampling_interval_s':.005,
                  'rss_scope':'launcher plus descendants; shared working-set pages may repeat',
                  'limits':'Startup only; GPU PID visibility is not a precise VRAM allocation measurement.'}
        output = ROOT/'docs/evidence/dev_scanner_2026-11-01.json'
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True,indent=2))
        return 0 if all(row['exit_code']==0 for row in rows) else 1
    finally:
        if gpu:
            gpu[0].nvmlShutdown()


if __name__=='__main__':
    raise SystemExit(main())
