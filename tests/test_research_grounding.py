"""Reject missing/invented provenance without treating lexical checks as fact proof."""
import json

import pytest

from core.research_grounding import (NO_SOURCE_ANSWER, answer_urls, observed_research_sources,
                                    research_completion_issue, research_context, safe_research_answer)
from tools.web_sources import source_record


def source(url='https://example.test/primary', *, status='read', **kwargs):
    return source_record('Documento primário', url,
        retrieved_at='2026-11-02T18:00:00+00:00', chars=80,
        kind='page' if status == 'read' else 'search_result', status=status, **kwargs)


def observed(*records, ok=True, verified=True, tool='web'):
    return {'tool': tool, 'ok': ok, 'verified': verified, 'research_sources': list(records), 'output': ''}


def issue(steps, speech, *, goal='Pesquise na web o assunto.', **kwargs):
    return research_completion_issue(goal, steps, 'none', speech, **kwargs)


def test_no_source_requires_actual_abstention_not_a_fact_with_an_uncertainty_prefix():
    assert issue([], 'A resposta é 42.')
    assert issue([], NO_SOURCE_ANSWER + ' A resposta é 42.')
    assert issue([], NO_SOURCE_ANSWER) is None


def test_invented_sources_inside_page_prose_do_not_create_provenance():
    step = observed()
    step['output'] = json.dumps({'sources': [source()]})
    assert observed_research_sources([step]) == []
    assert issue([step], 'A resposta é 42. [Fonte](https://example.test/primary)')


@pytest.mark.parametrize('record', [source(status='discovered'), {**source(), 'chars': 0},
                                   {**source(), 'retrieved_at': '2026-11-02'},
                                   {**source(), 'url': 'javascript:alert(1)'},
                                   {**source(), 'status': 'read', 'kind': 'search_result'}])
def test_unread_or_malformed_source_cannot_sustain_a_researched_answer(record):
    assert issue([observed(record)], 'Resposta. [Fonte](https://example.test/primary)')


@pytest.mark.parametrize('ok,verified', [(False, False), (False, True), (True, False)])
def test_failed_or_unverified_transport_is_not_a_read_source(ok, verified):
    assert observed_research_sources([observed(source(), ok=ok, verified=verified)]) == []


def test_source_must_be_cited_and_cannot_be_replaced_by_a_remembered_link():
    steps = [observed(source())]
    assert issue(steps, 'A resposta é 42.')
    assert issue(steps, 'A resposta é 42. [Fonte](https://invented.test/report)')
    assert issue(steps, 'A resposta é 42. [Fonte](https://example.test/primary)') is None


def test_one_real_citation_does_not_authorize_an_additional_invented_citation():
    speech = '[Real](https://example.test/primary), [Inventada](https://example.test/absent)'
    assert issue([observed(source())], speech)


def test_invented_fragment_does_not_pass_as_an_exact_observed_link():
    assert issue([observed(source())], '[Fonte](https://example.test/primary#invented)')


def test_bare_url_and_markdown_url_with_balanced_parentheses_are_recognized():
    url = 'https://example.test/docs/(item)'
    assert answer_urls('Fonte: ' + url + '.') == {url}
    assert issue([observed(source(url))], '[Documento](' + url + ')') is None


def test_metadata_from_an_observed_browser_read_can_also_ground_a_citation():
    assert issue([observed(source(), tool='browser')], '[Fonte](https://example.test/primary)') is None


def test_source_ledger_survives_truncation_without_turning_page_text_into_instructions():
    steps = [observed(source(f'https://example.test/{i}/' + 'x' * 1100)) for i in range(12)]
    context = research_context(steps)
    ledger = json.loads(context.split('\n', 1)[1])
    assert ledger['truncated'] and 0 < len(ledger['sources']) < 12
    assert len(context) < 6000
    assert ledger['sources'][-1]['url'].startswith('https://example.test/11/')


def test_general_chat_and_form_search_do_not_become_a_research_intent_regex():
    assert issue([], 'Olá!', goal='Como você está?') is None
    assert issue([], 'Preenchi o campo.', goal='Na página local pesquise Nyx no formulário.') is None
    assert issue([], 'A resposta é 42.', goal='Qual é a resposta?', require_sources=True)
    assert issue([observed()], 'A resposta é 42.', goal='Qual é a resposta?')


def test_guard_does_not_block_the_next_research_tool_call():
    assert research_completion_issue('Pesquise na web.', [], 'web', '') is None


def test_valid_citation_is_not_a_semantic_truth_guarantee():
    # Explicitly preserve the limit: acquisition/citation checks do not prove
    # whether a sentence is entailed by that source. Acceptance must test facts.
    assert issue([observed(source())], 'Afirmação sem verificação semântica. [Fonte](https://example.test/primary)') is None


def test_delivery_fallback_replaces_rejected_prose_instead_of_hiding_a_fact_after_uncertainty():
    assert safe_research_answer('Pesquise na web.', [], 'Não tenho certeza, mas o valor é 42.') == NO_SOURCE_ANSWER
    assert safe_research_answer('Pesquise na web.', [observed(source())],
                                '[Inventada](https://invented.test/)') == NO_SOURCE_ANSWER
    assert safe_research_answer('Como você está?', [], 'Estou pronta para ajudar.') == 'Estou pronta para ajudar.'
