"""Regression coverage for unsupported conclusions seen in real browser trials."""
import pytest

from core.browser_grounding import browser_sequence_issue


def step(action, output='', *, ok=True, verified=True, **extra):
    return {'tool': 'browser', 'params': {'action': action}, 'output': output,
            'ok': ok, 'verified': verified, **extra}


def test_switching_tab_does_not_establish_its_body_code():
    steps = [step('tabs', 'Origem Nyx'), step('switch_tab', 'Origem Nyx')]
    assert browser_sequence_issue('Troque para a aba Origem Nyx e informe seu código.',
                                  steps, 'none', 'O código é Origem.')


def test_read_before_navigation_does_not_ground_current_tab():
    steps = [step('read', 'Código 8091'), step('switch_tab', 'Outra aba')]
    assert browser_sequence_issue('Na aba atual, informe o código.', steps, 'none', 'O código é 8091.')


def test_failed_navigation_keeps_last_verified_page_content():
    steps = [step('read', 'Código 8091'), step('open', 'TIMEOUT', ok=False, verified=False)]
    assert browser_sequence_issue('Informe o código da página no navegador.', steps, 'none',
                                  'A outra página falhou. O código da página lida é 8091.') is None


@pytest.mark.parametrize('speech', ['O código é Origem.', 'O código é 7014.', 'O código é 7014; a URL termina em 8091.'])
def test_wrong_scalar_answer_is_rejected_even_without_completion_verb(speech):
    steps = [step('open'), step('read', 'Código da aba Origem: 8091')]
    assert browser_sequence_issue('Na aba Origem, informe seu código.', steps, 'none', speech)


@pytest.mark.parametrize('speech', ['O código é 8091.', '8091', 'O código da aba Origem: 8091.'])
def test_body_value_can_be_reported_without_an_extra_action(speech):
    steps = [step('open'), step('read', 'Título\nCódigo da aba Origem: 8091')]
    assert browser_sequence_issue('Na aba Origem, informe seu código.', steps, 'none', speech) is None


def test_unverified_read_is_not_factual_evidence():
    steps = [step('read', 'Código 8091', verified=False)]
    assert browser_sequence_issue('Informe o código em https://example.test/.', steps, 'none', 'Código 8091.')


def test_latest_read_supersedes_earlier_code_without_navigation():
    steps = [step('read', 'Código 8091'), step('read', 'Código 9025')]
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none', 'Código 8091.')
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none', 'Código 9025.') is None


def test_code_numbers_preserve_leading_zeroes():
    steps = [step('read', 'Código 0091')]
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none', 'Código 91.')
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none', 'Código 0091.') is None


def test_negated_example_does_not_become_a_code_value():
    steps = [step('read', 'O código não é 1234. Código: 8091')]
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none', 'Código 1234.')


def test_real_failed_read_can_end_with_an_honest_error():
    steps = [step('open'), step('read', 'TIMEOUT', ok=False, verified=False)]
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none',
                                  'Não consegui ler a página: TIMEOUT. Não tenho certeza do código.') is None
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none',
                                  'Não consegui ler, mas o código é 8091.')
    assert browser_sequence_issue('No navegador, informe o código.', steps, 'none',
                                  'Não consegui ler, mas o código é Origem.')


def test_download_requires_saved_file_evidence_not_link_or_page():
    goal = 'Abra https://example.test/ e baixe o arquivo do link.'
    assert browser_sequence_issue(goal, [step('open'), step('click')], 'none', 'Baixei o arquivo.')
    assert browser_sequence_issue(goal, [step('download', verified=False)], 'none', 'Baixei o arquivo.')
    assert browser_sequence_issue(goal, [step('download')], 'none', 'Baixei o arquivo.') is None


def test_failed_download_can_report_error_without_claiming_a_file():
    steps = [step('download', 'PERMISSION', ok=False, verified=False)]
    assert browser_sequence_issue('No navegador, baixe o arquivo.', steps, 'none',
                                  'Não consegui baixar o arquivo: PERMISSION.') is None


def test_play_and_pause_need_verified_states_in_that_order():
    goal = 'No navegador, reproduza a mídia e depois pause.'
    paused = step('media_pause', media_state='paused')
    playing = step('media_play', media_state='playing')
    assert browser_sequence_issue(goal, [paused], 'none', 'Pausei a mídia.')
    assert browser_sequence_issue(goal, [paused, playing], 'none', 'Pausei a mídia.')
    assert browser_sequence_issue(goal, [playing, paused], 'none', 'Pausei a mídia.') is None


def test_guard_only_applies_to_browser_completion_of_explicit_requests():
    steps = [step('read', 'Código 8091')]
    assert browser_sequence_issue('Explique como escrever código Python.', steps, 'none', 'Exemplo: print(1)') is None
    assert browser_sequence_issue('Informe o código no navegador.', steps, 'browser', '') is None
    assert browser_sequence_issue('Informe o código no navegador.', [], 'none', '')


def test_form_cannot_be_completed_by_clicking_submit_without_typing():
    assert browser_sequence_issue('No navegador, preencha Nome com Nyx e salve o cadastro.',
        [step('open'),step('inspect'),step('click',verified=False)],'none','Cadastro local concluído com sucesso.')
