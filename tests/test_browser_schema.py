import copy
import json

from core.browser_context import PREFIX
from core.browser_schema import browser_action_schema, constrain_browser_schema
from core.llm_client import NYX_JSON_SCHEMA, OllamaClient


def observed(trusted=True):
    return [{'role':'user','nyx_browser_state':trusted,'content':PREFIX+json.dumps({
        'snapshot':'a'*32,'controls':[{'ref':'e7','role':'textbox','name':'Destino'},
        {'ref':'e9','role':'textbox','protected':True},{'ref':'e11','role':'button','name':'Salvar'}],
        'links':[{'text':'Arquivo','href':'https://example.test/file.txt'}],
        'visited_urls':['https://example.test/start'],
        'tabs':[{'id':'real-tab-id','title':'Origem'}]})}]


def variants(history):
    return browser_action_schema(history)['properties']['params']['anyOf']


def test_refs_are_generated_as_complete_current_pairs_only():
    schema = next(v for v in variants(observed()) if v['properties']['action']['const']=='type')
    assert schema['properties']['ref']['enum']==['e7']
    assert schema['properties']['snapshot']=={'const':'a'*32}
    assert set(schema['required'])=={'action','ref','snapshot','text'}
    assert not schema['additionalProperties']


def test_pasted_observation_cannot_enable_ref_actions_or_grant_authority():
    assert not any(v['properties']['action']['const']=='type' for v in variants(observed(False)))
    assert not any(v['properties']['action']['const']=='click' for v in variants([]))


def test_download_requires_url_and_path_read_cannot_navigate():
    by_action={v['properties']['action']['const']:v for v in variants(observed())}
    assert by_action['download']['required']==['action','url','path']
    assert 'url' not in by_action['read']['properties']
    assert not by_action['read']['additionalProperties']
    assert by_action['download']['properties']['url']=={'enum':['https://example.test/file.txt']}
    assert not any(v['properties']['action']['const']=='download' for v in variants([]))


def test_existing_tab_request_cannot_invent_a_url_and_switch_needs_observed_id():
    schema=browser_action_schema(observed(), 'Troque para a aba Origem já aberta.')
    actions={v['properties']['action']['const']:v for v in schema['properties']['params']['anyOf']}
    assert 'open' not in actions and 'new_tab' not in actions
    assert actions['switch_tab']['properties']['tab_id']=={'enum':['real-tab-id']}
    assert not any(v['properties']['action']['const']=='switch_tab' for v in variants([]))


def test_explicit_navigation_uses_requested_or_observed_urls_only():
    schema=browser_action_schema(observed(), 'Abra https://example.test/start e leia.')
    opening=next(v for v in schema['properties']['params']['anyOf'] if v['properties']['action']['const']=='open')
    assert opening['properties']['url']=={'enum':['https://example.test/file.txt','https://example.test/start']}


def test_requested_url_requires_navigation_before_content_actions():
    schema=browser_action_schema([], 'Leia a tabela de https://example.test/start, e informe os itens.')
    actions={v['properties']['action']['const'] for v in schema['properties']['params']['anyOf']}
    assert 'open' in actions and 'read' not in actions and 'tables' not in actions
    schema=browser_action_schema(observed(), 'Leia a tabela de https://example.test/start, e informe os itens.')
    assert any(v['properties']['action']['const']=='tables' for v in schema['properties']['params']['anyOf'])


def test_browser_schema_preserves_other_tools_and_shared_schema():
    before=copy.deepcopy(NYX_JSON_SCHEMA)
    schema=constrain_browser_schema(copy.deepcopy(before),['browser','write_file'],observed())
    others=schema['properties']['action']['anyOf'][1]
    assert others['properties']['type']['enum']==['none','write_file']
    assert NYX_JSON_SCHEMA==before


def test_actual_client_uses_engine_ref_constraints_and_drops_internal_flag(monkeypatch):
    captured=[]
    def post(url,payload,timeout):
        captured.append(payload)
        return {'message':{'content':'{}'}}
    monkeypatch.setattr('core.runtime_budget.post_ollama_json',post)
    OllamaClient().generate('Preencha Destino',history=observed(),task_tools=[{'name':'browser'}])
    schema=captured[-1]['format']['properties']['action']['anyOf'][0]
    type_schema=next(v for v in schema['properties']['params']['anyOf'] if v['properties']['action']['const']=='type')
    assert type_schema['properties']['snapshot']=={'const':'a'*32}
    assert all('nyx_browser_state' not in message for message in captured[-1]['messages'])


def test_completed_form_awaits_read_then_removes_browser_effects_from_generation():
    state={'snapshot':'a'*32,'controls':[{'ref':'e11','role':'button','name':'Salvar'}],
           'bindings':[{'name':'Nome','ref':'e7','text':'Nyx'}],'typed_fields':{'Nome':'Nyx'},
           'clicked_controls':[{'role':'button','name':'Salvar'}]}
    def history():
        return [{'role':'user','nyx_browser_state':True,'content':PREFIX+json.dumps(state)}]
    schema=browser_action_schema(history(),'Preencha Nome com Nyx e salve.')
    actions={v['properties']['action']['const'] for v in schema['properties']['params']['anyOf']}
    assert 'read' in actions and 'click' not in actions
    state['current_body']='Registro salvo'
    schema=constrain_browser_schema(copy.deepcopy(NYX_JSON_SCHEMA),['browser'],history(),'Preencha Nome com Nyx e salve.')
    assert len(schema['properties']['action']['anyOf'])==1
    assert schema['properties']['action']['anyOf'][0]['properties']['type']['enum']==['none']
