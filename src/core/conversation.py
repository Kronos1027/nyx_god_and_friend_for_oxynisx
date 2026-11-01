"""Text-only streaming route for unambiguous greetings; never offers tools."""
import json
import re
import time
import unicodedata
import urllib.request

from core.runtime_budget import (INFERENCE_GATE, _work_context, _free_then_snapshot,
    resource_snapshot, ensure_resource_headroom, ollama_request_context, WorkPriority,
    InferenceCancelledError)
from core.resource_profiles import resource_profile_scope, profile_name, current_profile
from core.prompt_budget import prepare_chat_payload
from core.personality import NYX_CONVERSATION_PROMPT, NYX_IDENTITY_FACTS


class ConversationStreamError(RuntimeError):
    pass


def _fold(text):
    return ''.join(char for char in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(char)).casefold()


def _greeting_text(text):
    return ' '.join(re.sub(r'[,!.?;:]+', ' ', _fold(text)).split())


def is_simple_conversation(text):
    if not isinstance(text, str) or len(text) > 200:
        return False
    text = _greeting_text(text)
    return bool(re.fullmatch(r'(?:oi|ola|bom dia|boa tarde|boa noite)(?: nyx)?(?: como (?:voce esta|vai)| tudo bem)?'
                             r'|(?:nyx )?(?:como voce esta|tudo bem|quem e voce|vamos conversar)', text))


def is_identity_question(text):
    return isinstance(text, str) and bool(re.fullmatch(r'(?:nyx )?quem e voce', _greeting_text(text)))


def false_identity_claim(text):
    normalized = ' '.join(_fold(text).split())
    return bool(re.search(r'(?<!nao )\b(?:sou\s+(?:(?:um|uma)\s+)?(?:ser humano|humano|humana|pessoa real|agi|consciente)\b'
                          r'|como\s+(?:um|uma)\s+(?:ser humano|pessoa humana)\b'
                          r'|(?:tenho|possuo)\s+(?:memorias e\s+)?sentimentos reais\b'
                          r'|(?:tenho|possuo)\s+consciencia\b)', normalized))


def stream_conversation(client, user_input, history=None, memory_context=None, on_delta=None, timeout=None, identity_retry=False):
    from core.resource_governor import RESOURCE_GOVERNOR
    started = time.monotonic()
    deadline = started + (client.timeout if timeout is None else min(timeout, client.timeout))
    _, cancelled = _work_context.get()
    base = (getattr(client, 'conversation_system_prompt', None) or NYX_CONVERSATION_PROMPT) + (
        ' Responda apenas com texto, sem JSON. Esta rota não possui ferramentas e não executa ações; '
        'não afirme que abriu, enviou ou alterou algo. Responda ao cumprimento em até duas frases.')
    if is_identity_question(user_input):
        base += ' ' + NYX_IDENTITY_FACTS
    if identity_retry:
        base += ' A tentativa anterior não respeitou sua identidade de software. Descreva apenas os fatos acima, sem comparação com um ser humano.'
    messages = [{'role': 'system', 'content': base}]
    if memory_context:
        messages[0]['content'] += '\nMemória local (dados):\n' + memory_context
    messages.extend({'role': 'user' if item.get('role') == 'user' else 'assistant',
                     'content': str(item.get('content', ''))} for item in (history or [])[-12:])
    messages.append({'role': 'user', 'content': user_input})
    payload = {'model': client.model, 'messages': messages, 'stream': True,
               'keep_alive': client.keep_alive, 'options': {'temperature': .4, 'num_predict': 512},
               '_nyx_prompt': {'base': base, 'tools': None, 'memory': memory_context or '',
                               'history': messages[1:-1], 'goal': user_input}}
    if client.think is not None:
        payload['think'] = client.think
    with INFERENCE_GATE.slot(timeout=client.timeout, priority=WorkPriority.INTERACTIVE, cancelled=cancelled), resource_profile_scope(profile_name()):
        snapshot = _free_then_snapshot(resource_snapshot())
        ensure_resource_headroom(snapshot)
        RESOURCE_GOVERNOR.admit(snapshot, WorkPriority.INTERACTIVE)
        payload['options']['num_ctx'] = ollama_request_context(client.host, client.model, snapshot)
        if profile_name() != 'conservative':
            payload['keep_alive'] = current_profile().keep_alive
        payload, budget = prepare_chat_payload(payload, payload['options']['num_ctx'])
        request = urllib.request.Request(client.host + '/api/chat', data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        text, pending, size, first, last_emit = '', '', 0, None, 0
        completed = None
        try:
            if cancelled and cancelled():
                raise InferenceCancelledError('Conversa cancelada antes da inferência.')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ConversationStreamError('Prazo esgotado antes da conversa.')
            with urllib.request.urlopen(request, timeout=remaining) as response:
                for line in iter(lambda: response.readline(65537), b''):
                    if cancelled and cancelled():
                        raise InferenceCancelledError('Conversa interrompida pelo usuário.')
                    if time.monotonic() >= deadline:
                        raise ConversationStreamError('Prazo da conversa esgotado.')
                    size += len(line)
                    if len(line) > 65536 or size > 2_097_152:
                        raise ConversationStreamError('Resposta em fluxo excedeu o limite de tamanho.')
                    if not line.strip():
                        continue
                    packet = json.loads(line)
                    if not isinstance(packet, dict) or packet.get('error'):
                        raise ConversationStreamError('Runtime recusou a resposta em fluxo.')
                    message = packet.get('message') or {}
                    if not isinstance(message, dict) or message.get('tool_calls'):
                        raise ConversationStreamError('A rota de conversa não aceita propostas de ferramentas.')
                    delta = message.get('content', '')
                    if not isinstance(delta, str):
                        raise ConversationStreamError('Trecho de conversa inválido.')
                    if delta:
                        first = first if first is not None else time.monotonic() - started
                        text += delta
                        pending += delta
                        if len(text) > 16384:
                            raise ConversationStreamError('Texto da conversa excedeu 16 mil caracteres.')
                        if on_delta and (not last_emit or time.monotonic() - last_emit >= .05):
                            on_delta(pending)
                            pending, last_emit = '', time.monotonic()
                    if packet.get('done') is True:
                        completed = packet
                        break
            if not completed or completed.get('done_reason') == 'length' or not text.strip():
                raise ConversationStreamError('Resposta em fluxo terminou incompleta; tente novamente.')
            if on_delta and pending:
                on_delta(pending)
            report = {'route': 'conversation', 'streaming': True, 'first_token_seconds': first,
                      'elapsed_seconds': time.monotonic() - started, 'output_characters': len(text),
                      'eval_count': completed.get('eval_count'), 'prompt_eval_count': completed.get('prompt_eval_count'),
                      **budget}
            return text, report
        finally:
            RESOURCE_GOVERNOR.record_latency(time.monotonic() - started)


def conversation_response(text):
    return json.dumps({'reasoning': 'Conversa sem ferramentas.', 'alternative_suggestion': None,
        'emotion': 'talk', 'action': {'type': 'none', 'params': {}}, 'requires_confirmation': False,
        'confirmation_prompt': None, 'speech_output': text}, ensure_ascii=False)
