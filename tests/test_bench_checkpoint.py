import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.checkpoint import atomic_write, load_resume  # noqa: E402
from bench.catalog import Case  # noqa: E402


def test_atomic_checkpoint_retries_temporary_windows_share_denial(tmp_path, monkeypatch):
    target = tmp_path / 'progress.json'
    target.write_text('{"previous": true}')
    original = Path.replace
    attempts = []
    def replace(source, destination):
        attempts.append(1)
        if len(attempts) < 3:
            assert json.loads(target.read_text()) == {'previous': True}
            raise PermissionError('shared file')
        return original(source, destination)
    monkeypatch.setattr(Path, 'replace', replace)
    monkeypatch.setattr('bench.checkpoint.time.sleep', lambda _: None)
    atomic_write(target, {'rows': [1,2,3]})
    assert len(attempts) == 3
    assert json.loads(target.read_text()) == {'rows': [1,2,3]}


def test_failed_atomic_replace_preserves_previous_and_pending_bytes(tmp_path, monkeypatch):
    target = tmp_path / 'progress.json'
    target.write_text('{"previous": true}')
    def denied(*args):
        raise PermissionError('still held')
    monkeypatch.setattr(Path, 'replace', denied)
    monkeypatch.setattr('bench.checkpoint.time.sleep', lambda _: None)
    with pytest.raises(PermissionError):
        atomic_write(target, {'rows': [1]})
    assert json.loads(target.read_text()) == {'previous': True}
    pending = list(tmp_path.glob('.bench-tmp-*'))
    assert len(pending) == 1 and json.loads(pending[0].read_text()) == {'rows': [1]}


def test_resume_keeps_completed_rows_and_rejects_changed_runtime(tmp_path):
    case = Case('c1', 'conversation', 'Bom dia', 'resident', 'text', 120, 'R0', 'greeting')
    report = {'schema_version':1, 'model':'qwen', 'profile':'normal', 'runs':3,
              'manifest':[case.to_dict()], 'runtime_fingerprint':'original',
              'rows':[{'id':'c1','category':'conversation','run':1,'status':'PASS','ok':True}]}
    path = tmp_path / 'progress.json'
    atomic_write(path, report)
    loaded, done = load_resume(path, [case], 'qwen', 'normal', 3, 'original')
    assert loaded['rows'] == report['rows'] and done == {('c1',1)}
    with pytest.raises(ValueError, match='mudou'):
        load_resume(path, [case], 'qwen', 'normal', 3, 'different')
    report['rows'].append(report['rows'][0])
    atomic_write(path, report)
    with pytest.raises(ValueError, match='duplicado'):
        load_resume(path, [case], 'qwen', 'normal', 3, 'original')
