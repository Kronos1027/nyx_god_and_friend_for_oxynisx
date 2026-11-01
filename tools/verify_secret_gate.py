"""Exercise the installed offline scanner with disposable, synthetic data."""
import json
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    scanner = ROOT / '.local-deps/security-env/Scripts/detect-secrets-hook.exe'
    rows = []
    with tempfile.TemporaryDirectory(prefix='secret-gate-', dir=ROOT/'build/diagnostic') as temporary:
        directory = Path(temporary)
        candidate = directory/'fixture.py'
        for run in range(1, 4):
            for kind, text in [('clean', 'message = "fixture"\n'),
                               ('synthetic', 'api_key = "' + 'sk-' + 'A1b2C3d4'*6 + '"\n')]:
                candidate.write_text(text, encoding='utf-8')
                started = time.monotonic()
                result = subprocess.run([str(scanner), '--no-verify', str(candidate)],
                                        cwd=directory, capture_output=True, check=False)
                rows.append({'run':run, 'fixture':kind, 'exit_code':result.returncode,
                             'expected_exit_code':0 if kind == 'clean' else 1,
                             'elapsed_s':round(time.monotonic()-started, 4)})
    report = {'scope':'installed offline scanner, synthetic disposable fixture only',
              'credential_network_verification':False, 'rows':rows,
              'passed':all(row['exit_code']==row['expected_exit_code'] for row in rows)}
    output = ROOT/'docs/evidence/secret_gate_2026-11-01.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
