"""Verify real encrypted local snapshots survive denied cloud upload, no mocks."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from core.backup import BackupVault  # noqa: E402
from core.cloud_backup import CloudBackup  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    artifacts = ROOT / 'build/diagnostic'
    artifacts.mkdir(parents=True, exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='backup-suspension-', dir=artifacts))
    rows = []
    for index in range(1, 4):
        root = base / str(index)
        vault = BackupVault(root)
        snapshot = vault.create()
        before, key = snapshot.read_bytes(), vault.key_path.read_bytes()
        started = time.monotonic()
        error = ''
        try:
            CloudBackup(root).upload(snapshot)
        except PermissionError as exc:
            error = str(exc)
        unchanged = snapshot.read_bytes() == before and vault.key_path.read_bytes() == key
        no_cloud_work = not (root / 'data/cloud-backup').exists()
        # Independent file checks, not the production verifier or success metadata.
        rows.append({'run': index, 'upload_blocked': bool(error), 'error': error,
                     'elapsed_ms': round((time.monotonic()-started)*1000, 2),
                     'local_snapshot_and_key_unchanged': unchanged, 'no_cloud_work_directory': no_cloud_work,
                     'passed': bool(error) and unchanged and no_cloud_work})
    report = {'scope': 'three disposable real BackupVault snapshots; no personal data, real Git or mocks',
              'rows': rows, 'passed': all(row['passed'] for row in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
