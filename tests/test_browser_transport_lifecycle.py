import json
from types import SimpleNamespace

import pytest

from tools.browser_tool import BrowserSession, BrowserError


def test_launcher_exit_does_not_restart_or_change_live_tab(monkeypatch):
    session = BrowserSession()
    session._started = True
    session._process = SimpleNamespace(poll=lambda: 0)
    calls = []
    class Transport:
        def send(self, message):
            calls.append(json.loads(message))
        def recv(self):
            return json.dumps({'id': calls[-1]['id'], 'result': {'tab': 'original'}})
    session._ws = Transport()
    monkeypatch.setattr(session, 'start', lambda: pytest.fail('Não reiniciar sessão conectada.'))
    assert session._call('Page.getFrameTree') == {'tab': 'original'}
    assert session._call('Runtime.evaluate') == {'tab': 'original'}
    assert len(calls) == 2


def test_dead_transport_fails_without_replaying_command_in_new_session(monkeypatch):
    session = BrowserSession()
    session._started = True
    class Broken:
        def send(self, message):
            raise OSError('closed')
    session._ws = Broken()
    monkeypatch.setattr(session, 'start', lambda: pytest.fail('Não repetir em nova sessão.'))
    with pytest.raises(BrowserError, match='closed'):
        session._call('Input.dispatchMouseEvent')
