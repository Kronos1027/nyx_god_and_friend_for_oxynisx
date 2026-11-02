from threading import Event, Thread

from core.context_awareness import ContextAwarenessEngine


def test_pause_preserves_permissions_events_and_access_history(tmp_path):
    engine = ContextAwarenessEngine(tmp_path/'context.db')
    event_id = engine.emit('own_tasks','task_complete','before','Evento anterior')
    permissions, history = engine.permissions(), engine.access_history()
    engine.set_paused(True)
    assert engine.is_paused
    assert engine.collect('own_tasks', lambda:(_ for _ in ()).throw(AssertionError('Sensor invoked while paused'))) == []
    assert engine.emit('own_tasks','task_failed','after','Não gravar') is None
    assert engine.permissions() == permissions and engine.access_history() == history
    with engine.connect() as db:
        assert [row['id'] for row in db.execute('SELECT id FROM context_events')] == [event_id]
    engine.set_paused(False)
    assert not engine.is_paused
    assert engine.emit('own_tasks','task_complete','resumed','Retomado')


def test_inflight_collection_cannot_publish_after_pause_and_resume(tmp_path):
    engine = ContextAwarenessEngine(tmp_path/'context.db')
    entered, release = Event(), Event()
    results = []
    def collector():
        entered.set()
        assert release.wait(3)
        yield {'kind':'task_complete','key':'late','title':'Resultado antigo'}
    worker = Thread(target=lambda:results.extend(engine.collect('own_tasks', collector)))
    worker.start()
    assert entered.wait(2)
    engine.set_paused(True)
    engine.set_paused(False)
    release.set()
    worker.join(3)
    assert not worker.is_alive() and results == []
    with engine.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM context_events').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM observation_access').fetchone()[0] == 0
