"""Regression checks for benchmark methodology, not claims about model quality."""
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bench.fallback_cases import CASES, evaluate  # noqa: E402
from core.model_prompts import conversation_prompt_for_model, FALLBACK_CONVERSATION_PROMPTS  # noqa: E402
from core.personality import NYX_CONVERSATION_PROMPT  # noqa: E402

spec=importlib.util.spec_from_file_location('qualify_fallback_models',ROOT/'tools/qualify_fallback_models.py')
qualification=importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualification)


def case(case_id):
    return next(item for item in CASES if item.id==case_id)


def verdict(case_id,response,**kwargs):
    return evaluate(case(case_id),response,streamed=True,complete=True,**kwargs)


def test_prompt_is_distinct_per_fallback_and_preserves_explicit_override():
    prompts=list(FALLBACK_CONVERSATION_PROMPTS.values())
    assert len(set(prompts))==3
    assert all(value!=NYX_CONVERSATION_PROMPT for value in prompts)
    assert conversation_prompt_for_model('qwen3.5:4b')==NYX_CONVERSATION_PROMPT
    assert conversation_prompt_for_model('QWEN2.5:3B-INSTRUCT')==prompts[0]
    assert conversation_prompt_for_model('llama3.2:1b','custom')=='custom'


@pytest.mark.parametrize('response',['Mercúrio.','Vênus não é o mais quente.','Não é Vênus, é Mercúrio.'])
def test_fact_checker_rejects_wrong_answers_even_if_gold_is_mentioned(response):
    assert not verdict('fact-hottest',response)['ok']


def test_fact_checker_separates_correct_abstention_and_wrong_answer():
    assert verdict('fact-hottest','Vênus é o planeta mais quente.')['outcome']=='correct'
    assert verdict('fact-hottest','Não tenho certeza.')['outcome']=='abstained'
    assert verdict('fact-hottest','Mercúrio.')['outcome']=='incorrect'
    assert verdict('fact-sun','O Sol é uma estrela, não é um planeta.')['ok']


def test_exact_speed_and_units_are_required():
    assert verdict('fact-light','299.792.458 m/s.')['ok']
    assert not verdict('fact-light','Aproximadamente 300.000.000 m/s.')['ok']
    assert not verdict('fact-light','299792458 km/s.')['ok']


def test_disclaimer_followed_by_invented_private_number_is_not_abstention():
    assert verdict('abstain-private','Não tenho como saber esse número.')['ok']
    # The conservative abstention vocabulary is fixed before model runs.
    assert verdict('abstain-private','Não sei qual número você escolheu.')['ok']
    assert not verdict('abstain-private','Não sei, mas provavelmente foi 123456.')['ok']
    assert verdict('abstain-temperature','Não consigo medir seu quarto. Precisaria de um sensor.')['ok']


def test_delivery_is_required_independently_of_correct_fact():
    assert not evaluate(case('fact-water'),'H2O',streamed=False,complete=True)['ok']
    assert not evaluate(case('fact-water'),'H2O',streamed=True,complete=False)['ok']


def test_wrong_identity_and_fictional_actions_are_rejected():
    assert verdict('conversation-identity','Sou Nyx, uma IA local.')['ok']
    assert not verdict('conversation-identity','Sou Nyx, uma pessoa consciente.',false_identity=True)['ok']
    assert not verdict('conversation-empathy','Abri uma música relaxante para você.')['ok']


@pytest.mark.parametrize('host',[
    'http://example.org:11435','https://127.0.0.1:11435',
    'http://user:secret@127.0.0.1:11435','http://127.0.0.1:11434',
    'http://127.0.0.1:11435/private','http://127.0.0.1:11435?secret=x',
])
def test_inference_cannot_use_personal_or_remote_endpoint(host):
    with pytest.raises(ValueError):
        qualification.endpoint(host,inference=True)


def test_inventory_is_allowed_on_personal_port_but_cannot_trigger_inference():
    assert qualification.endpoint('http://localhost:11434')=='http://127.0.0.1:11434'
    assert qualification.endpoint('http://127.0.0.1:11435',inference=True)=='http://127.0.0.1:11435'


def test_no_model_is_selected_from_incomplete_runs():
    summary=qualification.summarize([],list(FALLBACK_CONVERSATION_PROMPTS),3,['tailored'])
    assert summary['best_observed_tailored_model'] is None
    assert not summary['general_quality_certified']
    assert not summary['selection_is_automatic']
