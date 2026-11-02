"""Privacy gates and publication races; native probes live in verify_presence.py."""
from threading import Event, Thread
import time

from core.context_awareness import ContextAwarenessEngine
from core.presence_sensors import PresenceMonitor, SENSOR_FIELDS, redact_window


def test_no_consent_never_invokes_external_sensor_or_writes_history(tmp_path):
    context = ContextAwarenessEngine(tmp_path/'context.db')
    def forbidden():
        raise AssertionError('External collector called without consent')
    monitor = PresenceMonitor(context, collectors={key: forbidden for key in SENSOR_FIELDS})
    monitor.resume()
    before = context.access_history()
    snapshot = monitor.collect(0)
    assert set(snapshot['fields']) == {'window', 'processes', 'media', 'game'}
    assert all(item['status'] == 'off' for item in snapshot['fields'].values())
    assert context.access_history() == before
    with context.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM context_events').fetchone()[0] == 0


def test_private_and_revoke_regrant_discard_inflight_content(tmp_path):
    context = ContextAwarenessEngine(tmp_path/'context.db')
    for operation in ('pause', 'permission'):
        context.set_permission('active_window', True)
        entered, release = Event(), Event()
        result = []
        def collector(entered=entered, release=release):
            entered.set()
            assert release.wait(3)
            return 'late private title'
        worker = Thread(target=lambda result=result, collector=collector: result.append(context.observe_now('active_window', collector)))
        worker.start()
        assert entered.wait(2)
        if operation == 'pause':
            context.set_paused(True)
            context.set_paused(False)
        else:
            context.set_permission('active_window', False)
            context.set_permission('active_window', True)
        release.set()
        worker.join(3)
        assert not worker.is_alive() and result == [None]


def test_monitor_pause_stops_next_collector_and_cannot_publish_old_sample(tmp_path):
    context = ContextAwarenessEngine(tmp_path/'context.db')
    for sensor in SENSOR_FIELDS:
        context.set_permission(sensor, True)
    entered, release, finished = Event(), Event(), Event()
    calls, published = [], []
    def first():
        calls.append('window')
        entered.set()
        assert release.wait(3)
        finished.set()
        return {'status': 'ok', 'text': 'old title'}
    def other():
        calls.append('other')
        return {'status': 'ok', 'text': 'not allowed'}
    monitor = PresenceMonitor(context, collectors={key: first if key == 'active_window' else other for key in SENSOR_FIELDS})
    monitor.resume()
    assert monitor.request(published.append)
    assert entered.wait(2)
    monitor.pause()
    monitor.resume()
    release.set()
    assert finished.wait(2)
    deadline = time.monotonic()+2
    while monitor._busy and time.monotonic() < deadline:
        time.sleep(.005)
    assert not monitor._busy and calls == ['window'] and published == []


def test_successful_transient_read_does_not_save_title_or_audit_collection(tmp_path):
    context = ContextAwarenessEngine(tmp_path/'context.db')
    context.set_permission('active_window', True)
    before = context.access_history()
    assert context.observe_now('active_window', lambda: 'unique private title') == 'unique private title'
    assert context.access_history() == before
    assert b'unique private title' not in context.database.read_bytes()


def test_game_profile_does_not_launch_media_or_enumerate_inventory(tmp_path, monkeypatch):
    context = ContextAwarenessEngine(tmp_path/'context.db')
    for key in ('media', 'process_inventory', 'games'):
        context.set_permission(key, True)
    def forbidden():
        raise AssertionError('Heavy sensor called in game profile')
    monkeypatch.setattr('core.presence_sensors.active_game', lambda: {'status':'empty', 'text':'No known foreground game'})
    monitor = PresenceMonitor(context, collectors={key: forbidden for key in SENSOR_FIELDS})
    monitor.set_lightweight(True)
    monitor.resume()
    snapshot = monitor.collect(1)
    assert snapshot['fields']['media']['status'] == 'paused'
    assert snapshot['fields']['processes']['status'] == 'paused'
    assert snapshot['fields']['game']['status'] == 'empty'


def test_sensitive_app_title_and_secrets_are_filtered():
    for app, title in (('Bitwarden.exe', 'Vault'), ('msedge.exe', 'InPrivate — Search'),
                       ('chrome.exe', 'Banco — Acesso'), ('browser.exe', 'Senha de acesso')):
        result = redact_window(app, title)
        assert result['status'] == 'protected'
        assert title not in result['text']
    result = redact_window('Editor.exe', 'Project token=example-secret-value')
    assert 'example-secret-value' not in result['text']
    assert result['status'] == 'ok'
    assert redact_window('chrome.exe', 'Unmarked private webpage')['status'] == 'protected'


def test_named_process_is_only_game_candidate_and_java_is_not_minecraft(monkeypatch):
    from core.presence_sensors import known_games
    monkeypatch.setattr('core.presence_sensors.process_names', lambda: ['javaw.exe', 'steam.exe'])
    assert known_games()['status'] == 'empty'
    monkeypatch.setattr('core.presence_sensors.process_names', lambda: ['cs2.exe'])
    assert known_games() == {'status': 'ok', 'text': 'Processo detectado: Counter-Strike 2'}


def test_context_snippet_rechecks_consent_expiry_and_pause(tmp_path):
    context = ContextAwarenessEngine(tmp_path/'context.db')
    context.set_permission('active_window', True)
    clock = [10.0]
    monitor = PresenceMonitor(context, clock=lambda: clock[0])
    monitor.resume()
    monitor._latest = {'generation': 0, 'observed_at': 10.0,
                       'fields': {'window': {'status': 'ok', 'text': 'Authorized title'}}}
    assert 'Authorized title' in monitor.context_snippet()
    context.set_permission('active_window', False)
    assert monitor.context_snippet() == ''
    context.set_permission('active_window', True)
    clock[0] = 31.0
    assert monitor.context_snippet() == ''
    clock[0] = 10.0
    monitor.pause()
    assert monitor.context_snippet() == ''


def test_stopped_window_observation_cannot_repopulate_cache(monkeypatch):
    from core.presence_sensors import ForegroundWindowSensor
    entered, release = Event(), Event()
    def read():
        entered.set()
        assert release.wait(3)
        return {'status': 'ok', 'text': 'Old private window'}
    monkeypatch.setattr('core.presence_sensors.active_window', read)
    sensor = ForegroundWindowSensor()
    results = []
    worker = Thread(target=lambda: results.append(sensor.read()))
    worker.start()
    assert entered.wait(2)
    sensor.stop()
    release.set()
    worker.join(3)
    assert not worker.is_alive() and results == [None] and sensor._cached is None


def test_pause_between_media_creation_and_start_prevents_popen(tmp_path, monkeypatch):
    import os
    import pytest
    if os.name != 'nt':
        pytest.skip('Windows subprocess launch policy')
    from core.windows_media import WindowsMediaSensor
    entered, release = Event(), Event()
    original = WindowsMediaSensor.read
    def delayed_read(self, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(self, **kwargs)
    monkeypatch.setattr(WindowsMediaSensor, 'read', delayed_read)
    def forbidden(*args, **kwargs):
        raise AssertionError('Helper launched after pause')
    monkeypatch.setattr('core.windows_media.subprocess.Popen', forbidden)
    context = ContextAwarenessEngine(tmp_path/'context.db')
    context.set_permission('media', True)
    monitor = PresenceMonitor(context)
    monitor.resume()
    results = []
    worker = Thread(target=lambda: results.append(monitor._read_media(0)))
    worker.start()
    assert entered.wait(2)
    monitor.pause()
    release.set()
    worker.join(3)
    assert not worker.is_alive() and results == [None]
    assert monitor._media._cached is None and monitor._media._process is None
