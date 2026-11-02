import json

from core.browser_context import PREFIX
from core.browser_fields import requested_fields
from core.browser_schema import browser_action_schema


def field(name,ref='e1'):
    return {'name':name,'ref':ref,'role':'textbox'}


def test_explicit_multiple_fields_preserve_exact_values_and_order():
    controls=[field('Nome'),field('Mensagem','e2')]
    result=requested_fields('Abra https://example.test/, preencha Nome com Nyx ação 1 e Mensagem com Olá mundo, e salve pelo botão.',controls)
    assert result==[{'name':'Nome','ref':'e1','text':'Nyx ação 1'},{'name':'Mensagem','ref':'e2','text':'Olá mundo'}]


def test_frame_context_does_not_become_part_of_field_value():
    assert requested_fields('Preencha Destino iframe, dentro do quadro Cadastro, com Nyx ação 2.',[field('Destino iframe')])[0]['text']=='Nyx ação 2'


def test_quoted_punctuation_is_retained_and_ambiguous_labels_are_not_bound():
    assert requested_fields('Preencha Mensagem com "Olá, mundo. Tudo bem?".',[field('Mensagem')])[0]['text']=='Olá, mundo. Tudo bem?'
    assert requested_fields('Preencha Nome com Nyx.',[field('Nome'),field('Nome','e2')])==[]


def test_simple_form_search_binds_only_a_unique_observed_textbox():
    assert requested_fields('Na página pesquise astronomia no formulário.',[field('Pesquisar')])[0]['text']=='astronomia'
    assert requested_fields('Na página pesquise astronomia no formulário.',[field('Pesquisar'),field('Outro','e2')])==[]


def test_negated_or_descriptive_field_mentions_do_not_force_typing():
    assert requested_fields('Não preencha Nome com Nyx.',[field('Nome')])==[]
    assert requested_fields('Nunca digite Nome com Nyx.',[field('Nome')])==[]
    assert requested_fields('Explique um formulário que associa Nome com Nyx.',[field('Nome')])==[]


def test_schema_prevents_submitting_explicit_fields_before_verified_typing():
    state={'snapshot':'a'*32,'controls':[field('Nome'),{'name':'Salvar','ref':'e3','role':'button'}],
           'bindings':[{'name':'Nome','ref':'e1','text':'Nyx'}]}
    def schema():
        return browser_action_schema([{'role':'user','nyx_browser_state':True,'content':PREFIX+json.dumps(state)}])['properties']['params']['anyOf']
    choices=schema()
    assert not any(v['properties']['action']['const']=='click' for v in choices)
    typing=next(v for v in choices if v['properties']['action']['const']=='type')
    assert typing['properties']['text']=={'const':'Nyx'}
    state['typed_fields']={'Nome':'Nyx'}
    assert any(v['properties']['action']['const']=='click' for v in schema())
    assert not any(v['properties']['action']['const']=='type' for v in schema())
