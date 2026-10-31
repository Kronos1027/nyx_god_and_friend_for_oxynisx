from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from audit.logger import AuditLogger


def test_task_trace_does_not_leak_context_between_threads_or_after_scope(tmp_path):
    audit = AuditLogger(tmp_path)
    ids = ['a' * 32, 'b' * 32]
    def run(task_id):
        with audit.task_scope(task_id):
            audit.log_event('observation', marker=task_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, ids))
    audit.log_event('unrelated')
    for task_id in ids:
        lines = (tmp_path / 'traces' / f'{task_id}.jsonl').read_text(encoding='utf-8').splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])['marker'] == task_id
    assert 'task_id' not in audit.read_all()[-1]


def test_task_trace_rejects_path_traversal_and_restores_scope_on_error(tmp_path):
    audit = AuditLogger(tmp_path)
    with pytest.raises(ValueError), audit.task_scope('../outside'):
        pass
    with pytest.raises(RuntimeError), audit.task_scope('c' * 32):
        raise RuntimeError('stop')
    assert 'task_id' not in audit.log_event('after_error')
