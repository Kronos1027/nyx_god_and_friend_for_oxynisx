"""Apply the user-approved cloud-backup preference suspension, preserving data."""
import argparse
import json
import os
from pathlib import Path

from PyQt6.QtCore import QSettings

ROOT = Path(__file__).resolve().parents[1]


def file_state(root):
    paths = list((root / 'data/backups').glob('*.nyxbackup'))
    key = root / 'data/backup-recovery.key'
    if key.exists():
        paths.append(key)
    return {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Alterar somente cloud_backup=false nos INIs existentes.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    targets = [('source', ROOT)]
    if os.environ.get('LOCALAPPDATA'):
        targets.append(('installed', Path(os.environ['LOCALAPPDATA']) / 'Nyx'))
    report = {'applied': args.apply, 'targets': [], 'remote_history_changed': False,
              'running_instances_restarted': False, 'note': 'Instâncias antigas já abertas podem precisar ser reiniciadas pelo usuário.'}
    for label, root in targets:
        ini = root / 'data/desktop.ini'
        row = {'scope': label, 'settings_existed': ini.is_file()}
        if ini.is_file():
            files_before = file_state(root)
            settings = QSettings(str(ini), QSettings.Format.IniFormat)
            before = {key: settings.value(key) for key in settings.allKeys() if key != 'cloud_backup'}
            row['cloud_enabled_before'] = settings.value('cloud_backup', True, type=bool)
            if args.apply:
                settings.setValue('cloud_backup', False)
                settings.sync()
                if settings.status() != QSettings.Status.NoError:
                    raise RuntimeError('Não foi possível persistir a preferência de backup.')
            row['cloud_enabled_after'] = settings.value('cloud_backup', True, type=bool)
            row['other_preferences_unchanged'] = before == {key: settings.value(key) for key in settings.allKeys() if key != 'cloud_backup'}
            row['backup_and_key_metadata_unchanged'] = files_before == file_state(root)
        report['targets'].append(row)
    report['passed'] = all(not row['settings_existed'] or
                          (row['other_preferences_unchanged'] and row['backup_and_key_metadata_unchanged']
                           and (not args.apply or not row['cloud_enabled_after'])) for row in report['targets'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
