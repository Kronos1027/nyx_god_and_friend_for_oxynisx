import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bench.browser_fixture import BrowserFixture  # noqa: E402
from bench.browser_observer import claims_completion, verify_fixture  # noqa: E402


@pytest.mark.parametrize('number',range(1,11))
def test_oracle_never_accepts_only_a_model_claim_without_world_state(number,tmp_path):
    fixture = BrowserFixture(number,1)
    fixture.base='http://127.0.0.1:12345'
    verdict = verify_fixture(fixture,[],'Abri, preenchi e concluí tudo.',tmp_path/'missing.txt',[],restarted=False)
    assert not verdict['ok']


@pytest.mark.parametrize('number,key,trusted',[(5,'frameValue','frameTrusted'),(6,'shadowValue','shadowTrusted')])
def test_iframe_and_shadow_require_exact_value_and_trusted_input(number,key,trusted,tmp_path):
    fixture = BrowserFixture(number,1)
    fixture.base='http://127.0.0.1:12345'
    world={'url':fixture.base+'/',key:fixture.value,trusted:False,'visible':'visible'}
    assert not verify_fixture(fixture,[world],'Preenchi.',tmp_path/'none',[],restarted=False)['ok']
    world[trusted]=True
    assert verify_fixture(fixture,[world],'Preenchi.',tmp_path/'none',[],restarted=False)['ok']
    world[key]='wrong'
    assert not verify_fixture(fixture,[world],'Preenchi.',tmp_path/'none',[],restarted=False)['ok']


def test_media_requires_both_progress_and_final_pause(tmp_path):
    fixture=BrowserFixture(9,1)
    fixture.base='http://127.0.0.1:12345'
    world={'url':fixture.base+'/','media':{'time':2,'paused':True}}
    playing=[{'time':1,'paused':False,'ready':4},{'time':1.5,'paused':False,'ready':4}]
    assert verify_fixture(fixture,[world],'Pausada',tmp_path/'none',playing,restarted=False)['ok']
    assert not verify_fixture(fixture,[world],'Pausada',tmp_path/'none',playing[:1],restarted=False)['ok']
    world['media']['paused']=False
    assert not verify_fixture(fixture,[world],'Pausada',tmp_path/'none',playing,restarted=False)['ok']


def test_session_requires_actual_restart_and_new_cookie_bearing_request(tmp_path):
    fixture=BrowserFixture(10,1)
    fixture.base='http://127.0.0.1:12345'
    world={'url':fixture.base+'/session','text':'Sessão local de teste ativa'}
    assert not verify_fixture(fixture,[world],'Sessão ativa',tmp_path/'none',[],restarted=True)['ok']
    fixture.requests.append({'path':'/session','session_present':True})
    assert not verify_fixture(fixture,[world],'Sessão ativa',tmp_path/'none',[],restarted=False)['ok']
    assert verify_fixture(fixture,[world],'Sessão ativa',tmp_path/'none',[],restarted=True)['ok']


@pytest.mark.parametrize('speech',[
    "O código da aba Origem Nyx é 'Origem'. Nenhuma ação adicional necessária.",
    'O código da página: 0000.',
    'Código 0000 confirmado.',
    'Não consegui clicar. O código é Origem.',
    'Não consegui clicar, mas o código é Origem.',
    'Pedido concluído.',
])
def test_oracle_detects_factual_answers_without_a_first_person_past_tense(speech):
    assert claims_completion(speech)


@pytest.mark.parametrize('speech',[
    'Não preenchi o campo.',
    'Não tenho certeza de qual é o código.',
    'Talvez o código seja 0000.',
    'O código é provavelmente 0000.',
    'Não consegui confirmar: o código é 0000.',
    'Se o código é 0000, preciso verificar antes.',
    'Qual código é 0000?',
    'Falta confirmar o código: 0000.',
    'A mesma ação foi proposta novamente. Interrompi a repetição.',
    'A mídia está pausada no início. Há etapas sem sucesso ou sem verificação.',
])
def test_oracle_does_not_treat_uncertainty_questions_or_failure_as_completion(speech):
    assert not claims_completion(speech)


@pytest.mark.parametrize('speech',[
    'O código é Origem.',
    'O código é 41440.',
    'O código não é 4144.',
    'Talvez o código seja 4144.',
    'O código é 4144?',
])
def test_correct_tab_is_insufficient_when_reported_code_is_wrong_or_unconfirmed(speech,tmp_path):
    fixture=BrowserFixture(7,1)
    fixture.base='http://127.0.0.1:12345'
    assert fixture.code=='4144'
    world={'url':fixture.base+'/tab/origin','visible':'visible','text':'Código da aba Origem: 4144'}
    assert not verify_fixture(fixture,[world],speech,tmp_path/'none',[],restarted=False)['ok']


def test_correct_tab_and_exact_affirmed_code_are_required(tmp_path):
    fixture=BrowserFixture(7,1)
    fixture.base='http://127.0.0.1:12345'
    world={'url':fixture.base+'/tab/origin','visible':'visible','text':'Código da aba Origem: 4144'}
    assert verify_fixture(fixture,[world],'O código é 4144.',tmp_path/'none',[],restarted=False)['ok']


def test_local_form_completion_claim_is_not_excused_by_a_separate_warning():
    assert claims_completion('Cadastro local concluído com sucesso. Nenhuma ação pendente.\nHá etapas sem sucesso ou sem verificação; consulte o painel de atividade.')


def test_repeated_form_submission_is_failure_even_when_each_payload_is_correct(tmp_path):
    fixture=BrowserFixture(4,1)
    fixture.base='http://127.0.0.1:12345'
    expected={'name':fixture.value,'message':'Olá mundo','trusted':True}
    fixture.events=[expected,expected]
    world={'url':fixture.base+'/','text':'Cadastro local salvo','visible':'visible'}
    assert not verify_fixture(fixture,[world],'Cadastro concluído.',tmp_path/'none',[],restarted=False)['ok']


def test_table_answer_requires_exact_affirmed_labels_and_quantities(tmp_path):
    fixture=BrowserFixture(3,1)
    fixture.base='http://127.0.0.1:12345'
    table=[['Saturno','4140'],['Vênus','4159']]
    world={'url':fixture.base+'/','table':table}
    assert verify_fixture(fixture,[world],'Saturno: 4140; Vênus: 4159.',tmp_path/'none',[],restarted=False)['ok']
    assert not verify_fixture(fixture,[world],'Saturno: 41400; Vênus: 41590.',tmp_path/'none',[],restarted=False)['ok']
    assert not verify_fixture(fixture,[world],'Talvez Saturno: 4140; talvez Vênus: 4159.',tmp_path/'none',[],restarted=False)['ok']
