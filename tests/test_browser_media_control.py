import pytest

from core.operation_control import OperationControl
from tools.browser_tool import BrowserError, BrowserSession


def session_with_calls(monkeypatch, exception=None, media_count=1):
    session=object.__new__(BrowserSession)
    session.control=OperationControl()
    calls=[]
    states=iter([{'source':'https://fixture.test/tone.wav','time':1,'paused':False,'ended':False,
                  'muted':False,'volume':.01,'ready':4,'connected':True},
                 {'source':'https://fixture.test/tone.wav','time':1.4,'paused':False,'ended':False,
                  'muted':False,'volume':.01,'ready':4,'connected':True}])
    def call(method,params):
        calls.append((method,params))
        if method=='Runtime.evaluate':
            if media_count!=1:
                return {'exceptionDetails':{'exception':{'description':'AMBIGUOUS: escolha uma mídia.'}}}
            return {'result':{'objectId':'media-object'}}
        if method=='Runtime.callFunctionOn':
            return {'exceptionDetails':{'exception':{'description':exception}}} if exception else {'result':{'value':True}}
        return {}
    session._call=call
    session._on_element=lambda *args:next(states)
    monkeypatch.setattr('tools.browser_tool.time.sleep',lambda seconds:None)
    return session,calls


def test_media_without_visual_controls_uses_unique_element_and_observed_time(monkeypatch):
    session,calls=session_with_calls(monkeypatch)
    result=session.control_media('play')
    assert result['verified'] and result['state']=='playing'
    invocation=next(p for method,p in calls if method=='Runtime.callFunctionOn')
    assert invocation['userGesture'] and invocation['awaitPromise']
    assert calls[-1][0]=='Runtime.releaseObject'


def test_media_play_rejection_is_reported_and_object_is_released(monkeypatch):
    session,calls=session_with_calls(monkeypatch,'NotAllowedError: reprodução recusada')
    with pytest.raises(BrowserError,match='reprodução recusada'):
        session.control_media('play')
    assert calls[-1][0]=='Runtime.releaseObject'


def test_multiple_media_never_choose_first_silently(monkeypatch):
    session,calls=session_with_calls(monkeypatch,media_count=2)
    with pytest.raises(BrowserError,match='AMBIGUOUS'):
        session.control_media('play')
    assert len(calls)==1
