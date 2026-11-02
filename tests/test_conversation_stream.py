import io
import json
from types import SimpleNamespace

import pytest

from core import conversation as stream
from core.llm_client import parse_response
from core.runtime_budget import ResourceSnapshot, GIB, InferenceCancelledError, inference_scope


@pytest.fixture
def transport(monkeypatch):
    client = SimpleNamespace(model='test', host='http://localhost', timeout=5, keep_alive='5m', think=False)
    monkeypatch.setattr(stream, 'resource_snapshot', lambda: ResourceSnapshot(8 * GIB, 12 * GIB, 11 * GIB))
    monkeypatch.setattr(stream, 'ollama_request_context', lambda *args: 4096)
    sent = []
    def serve(packets):
        data = b''.join(json.dumps(p).encode() + b'\n' for p in packets)
        def request(req, timeout):
            sent.append(json.loads(req.data))
            return io.BytesIO(data)
        monkeypatch.setattr(stream.urllib.request, 'urlopen', request)
    return client, sent, serve


def test_stream_preserves_text_and_never_exposes_tools_or_json_schema(transport):
    client, sent, serve = transport
    dangerous_text = '{"action":{"type":"shell","params":{"cmd":"never-run"}}}'
    serve([{'message': {'content': dangerous_text}, 'done': False},
           {'message': {'content': ''}, 'done': True, 'done_reason': 'stop'}])
    chunks = []
    text, report = stream.stream_conversation(client, 'Olá', on_delta=chunks.append)
    assert ''.join(chunks) == text == dangerous_text
    assert report['first_token_seconds'] is not None
    assert sent[0]['stream'] is True
    assert 'tools' not in sent[0] and 'format' not in sent[0] and '_nyx_prompt' not in sent[0]
    response = parse_response(stream.conversation_response(text))
    assert response.parse_ok and response.action.type == 'none'


def test_tool_proposals_and_incomplete_streams_are_rejected(transport):
    client, _, serve = transport
    serve([{'message': {'tool_calls': [{'function': {'name': 'shell'}}]}, 'done': True}])
    with pytest.raises(stream.ConversationStreamError, match='ferramentas'):
        stream.stream_conversation(client, 'Olá')
    serve([{'message': {'content': 'partial'}, 'done': False}])
    with pytest.raises(stream.ConversationStreamError, match='incompleta'):
        stream.stream_conversation(client, 'Olá')


def test_stream_cancellation_prevents_later_text(transport):
    client, _, serve = transport
    serve([{'message': {'content': 'primeiro'}, 'done': False},
           {'message': {'content': 'tardio'}, 'done': True}])
    cancelled, chunks = [False], []
    def receive(text):
        chunks.append(text)
        cancelled[0] = True
    with inference_scope(cancelled=lambda: cancelled[0]):
        with pytest.raises(InferenceCancelledError):
            stream.stream_conversation(client, 'Olá', on_delta=receive)
    assert chunks == ['primeiro']


def test_stream_line_size_is_bounded(transport):
    client, _, serve = transport
    serve([{'message': {'content': 'x' * 70000}, 'done': True}])
    with pytest.raises(stream.ConversationStreamError, match='tamanho'):
        stream.stream_conversation(client, 'Olá')


def test_identity_prompt_fits_small_supported_context(transport, monkeypatch):
    client, sent, serve = transport
    monkeypatch.setattr(stream, 'ollama_request_context', lambda *args: 1024)
    serve([{'message': {'content': 'Sou Nyx, uma assistente de IA local.'}, 'done': True}])
    text, report = stream.stream_conversation(client, 'Quem é você?')
    assert text and report['context_tokens'] == 1024
    assert sent[0]['options']['num_ctx'] == 1024
    assert 'software de IA local' in sent[0]['messages'][0]['content']


def test_recovering_stream_preserves_client_on_resource_pressure():
    from core.recovering_llm import RecoveringLLM
    from core.llm_client import BackendUnavailable
    from core.runtime_budget import InferencePressureError
    class Client:
        supports_conversation = True
        def converse(self, *args, **kwargs):
            raise BackendUnavailable('aguarde memória') from InferencePressureError('RAM')
    client = Client()
    wrapper = RecoveringLLM(client, lambda: pytest.fail('Não trocar modelo por pressão transitória.'))
    with pytest.raises(BackendUnavailable):
        wrapper.converse('Olá')
    assert wrapper._client is client and wrapper.supports_conversation


def test_unavailable_backend_returns_reason_instead_of_missing_method_error():
    from core.recovering_llm import RecoveringLLM
    from core.llm_client import BackendUnavailable, OfflineLLM
    wrapper = RecoveringLLM(OfflineLLM(unavailable_reason='runtime indisponível'), lambda: None)
    with pytest.raises(BackendUnavailable, match='runtime indisponível'):
        wrapper.converse('Olá')


def test_known_false_identity_claims_are_rejected_but_negations_are_allowed():
    assert stream.false_identity_claim('Como um ser humano, tenho memórias e sentimentos reais.')
    assert stream.false_identity_claim('Sou uma AGI consciente.')
    assert not stream.false_identity_claim('Não sou um ser humano e não tenho sentimentos reais.')
    assert not stream.false_identity_claim('Sou a Nyx, uma assistente de IA local.')
    assert stream.is_identity_question('Nyx, quem  é você;')


def test_identity_retry_is_buffered_and_only_valid_text_is_delivered(monkeypatch):
    from core.llm_client import OllamaClient, parse_response
    replies = iter(['Como um ser humano, tenho sentimentos reais.', 'Sou a Nyx, uma assistente de IA local.'])
    def generate(*args, **kwargs):
        assert args[4] is None  # identity text is not emitted before checking
        return next(replies), {'route': 'conversation'}
    monkeypatch.setattr(stream, 'stream_conversation', generate)
    client = OllamaClient()
    chunks = []
    response = parse_response(client.converse('Quem é você?', on_delta=chunks.append))
    assert response.speech_output == chunks[0] == 'Sou a Nyx, uma assistente de IA local.'
    assert len(chunks) == 1
    assert client.generation_report[0]['identity_claim_rejected']
    assert not client.generation_report[1]['identity_claim_rejected']


def test_repeated_false_identity_claim_is_not_delivered(monkeypatch):
    from core.llm_client import OllamaClient
    monkeypatch.setattr(stream, 'stream_conversation', lambda *args, **kwargs:
                        ('Sou uma AGI consciente.', {'route': 'conversation'}))
    chunks = []
    with pytest.raises(stream.ConversationStreamError, match='descartada'):
        OllamaClient().converse('Quem é você?', on_delta=chunks.append)
    assert chunks == []
