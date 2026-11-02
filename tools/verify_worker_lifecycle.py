"""Measure real UIA helper identity/startup/cleanup without operating any app."""
import json
from pathlib import Path
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from core.operation_control import OperationControl  # noqa: E402
from tools.windows_client import WindowsAutomationClient  # noqa: E402


def main():
    output = ROOT/'docs/evidence/worker_lifecycle_2026-11-01.json'
    if output.exists():
        raise FileExistsError('Evidência existente; preserve o resultado anterior.')
    rows = []
    for run in range(1,4):
        client = WindowsAutomationClient(OperationControl())
        started = time.monotonic()
        try:
            client._start()
            startup = time.monotonic()-started
            owned = dict(client._owned_pids)
            redirected = client._worker_pid != client._process.pid
            rss = 0
            for pid, created in owned.items():
                member = psutil.Process(pid)
                if member.create_time() == created:
                    rss += member.memory_info().rss
        finally:
            close_started = time.monotonic()
            client.close()
        remaining = 0
        for pid, created in owned.items():
            try:
                remaining += psutil.Process(pid).create_time() == created
            except psutil.NoSuchProcess:
                pass
        rows.append({'run':run, 'startup_s':round(startup,4),
                     'close_s':round(time.monotonic()-close_started,4),
                     'owned_process_count':len(owned), 'redirected_launcher':redirected,
                     'owned_rss_mib':round(rss/2**20,2), 'remaining_after_close':remaining})
    report = {'scope':'real production helper, no desktop mutations or application launch',
              'rows':rows, 'passed':all(row['remaining_after_close']==0 for row in rows),
              'limits':'RSS snapshot sums working sets and may repeat shared pages; not peak UI RAM/VRAM.'}
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
