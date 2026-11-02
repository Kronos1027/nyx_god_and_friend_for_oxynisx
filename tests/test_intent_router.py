import json
from types import SimpleNamespace

import pytest

from core import intent_router as router
from core.runtime_budget import InferenceCancelledError, InferencePressureError


@pytest.fixture
def classifier(monkeypatch):
    sent = []
    def serve(content, **extra):
        def request(url, payload, timeout):
            sent.append(payload)
            return {'message': {'content': content}, 'done': True, **extra}
        monkeypatch.setattr(router.runtime_budget, 'post_ollama_json', request)
    return SimpleNamespace(model='local', host='http://localhost', timeout=30, keep_alive='5m', think=False), sent, serve


@pytest.mark.parametrize('intent,route,fallback', [('conversation','conversation',False),
                                                ('task','task',False),('uncertain','task',True)])
def test_semantic_model_decides_route_with_history_and_no_tools(classifier, intent, route, fallback):
    client, sent, serve = classifier
    serve(json.dumps({'intent': intent}))
    history = [{'role':'assistant','content':'Falávamos de astronomia.'}]
    report = router.classify_intent(client, 'E as estrelas?', history)
    assert report['route'] == route and report['fallback'] == fallback
    assert sent[0]['messages'][1] == history[0]
    assert sent[0]['messages'][-1]['content'] == 'E as estrelas?'
    assert 'tools' not in sent[0] and sent[0]['options']['num_predict'] == 32


@pytest.mark.parametrize('content,extra', [('{"intent":"conversation","intent":"task"}', {}),
    ('{"intent":"conversation","action":"shell"}', {}), ('[]', {}), ('{"intent":"other"}', {}),
    ('{"intent":"conversation"}', {'done':False}),
    ('{"intent":"conversation"}', {'done_reason':'length'})])
def test_invalid_or_truncated_classification_falls_back_to_planner(classifier, content, extra):
    client, _, serve = classifier
    serve(content, **extra)
    report = router.classify_intent(client, 'Vamos conversar')
    assert report['route'] == 'task' and report['fallback']


def test_long_request_is_never_cropped_before_routing(classifier):
    client, sent, _ = classifier
    report = router.classify_intent(client, 'x'*4001 + ' apague os arquivos')
    assert report['route'] == 'task' and report['reason'] == 'context_requires_planner'
    assert not sent


@pytest.mark.parametrize('error', [InferenceCancelledError, InferencePressureError])
def test_router_preserves_stop_and_resource_safeguards(classifier, monkeypatch, error):
    client, _, _ = classifier
    def refuse(*args):
        raise error('stop')
    monkeypatch.setattr(router.runtime_budget, 'post_ollama_json', refuse)
    with pytest.raises(error):
        router.classify_intent(client, 'Olá')


def test_recovering_wrapper_delegates_and_unavailable_router_does_not_guess():
    from core.recovering_llm import RecoveringLLM
    client = SimpleNamespace(classify_intent=lambda text, history: {'route':'conversation', 'history':history})
    wrapper = RecoveringLLM(client, lambda: None)
    assert wrapper.classify_intent('explique', history=[]) == {'route':'conversation','history':[]}
    wrapper._client = SimpleNamespace()
    assert wrapper.classify_intent('oi')['route'] == 'task'
