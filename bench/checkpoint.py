"""Atomic progress and explicit resume for the read-only benchmark routes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def runtime_fingerprint(root):
    digest = hashlib.sha256()
    for path in [*sorted((root / 'src').rglob('*.py')), root / 'bench/verifiers.py', root / 'bench/native_windows.py']:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def atomic_write(path, report):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.bench-tmp-', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                # Pending bytes remain for diagnosis; previous report is intact.
                raise
            time.sleep(.05)


def completed_keys(report, manifest, repetitions):
    expected = {case.id: case for case in manifest}
    seen = set()
    for row in report['rows']:
        key = row['id'], row['run']
        case = expected.get(row['id'])
        if (case is None or row['category'] != case.category or type(row['run']) is not int
                or not 1 <= row['run'] <= repetitions or key in seen):
            raise ValueError('Checkpoint contém caso/rodada incompatível ou duplicado; nada será repetido.')
        if (type(row['ok']) is not bool or row['status'] not in
                {'PASS', 'FAIL', 'ERROR', 'BLOCKED_HARNESS', 'BLOCKED_RUNTIME'}
                or row['ok'] != (row['status'] == 'PASS')):
            raise ValueError('Resultado de checkpoint inconsistente; revise o relatório.')
        seen.add(key)
    return seen


def load_resume(path, manifest, model, profile, repetitions, fingerprint):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    if (report.get('schema_version') != 1 or report.get('model') != model
            or report.get('profile') != profile or report.get('runs') != repetitions
            or report.get('manifest') != [case.to_dict() for case in manifest]):
        raise ValueError('Modelo/perfil/manifesto/rodadas diferem do checkpoint. Use um relatório novo.')
    if report.get('runtime_fingerprint', fingerprint) != fingerprint:
        raise ValueError('Runtime ou verificador mudou desde o checkpoint; use um relatório novo.')
    done = completed_keys(report, manifest, repetitions)
    if any(case.route and case.route not in {'file_sum', 'greeting', 'identity'}
           for case in manifest if any((case.id, run) not in done for run in range(1, repetitions+1))):
        raise ValueError('Retomada automática restrita a casos de leitura/conversa; efeitos exigem revisão.')
    if 'runtime_fingerprint' not in report:
        report['legacy_checkpoint_note'] = 'Checkpoint inicial sem fingerprint; retomada diagnóstica, sem promover marco completo.'
    report['runtime_fingerprint'] = fingerprint
    return report, done
