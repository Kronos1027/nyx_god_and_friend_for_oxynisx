import json

from core.browser_context import compact_browser_observation, compact_browser_targets, browser_planning_state


def test_compact_observation_keeps_field_refs_snapshot_and_protection():
    data={'snapshot':'a'*32,'tree':[{'ref':'e1','role':'heading','name':'Title'},
        {'ref':'e8','role':'textbox','name':'Nome','states':{},'protected':False},
        {'ref':'e9','role':'textbox','name':'[campo protegido]','protected':True}],
        'url':'https://example.test','expires_seconds':30}
    compact=json.loads(compact_browser_observation(json.dumps(data)))
    assert compact['snapshot']==data['snapshot']
    assert [r['ref'] for r in compact['controls']]==['e8','e9']
    assert compact['controls'][1]['protected']
    assert 'snapshot' in compact['ref_usage']


def test_observation_limit_keeps_valid_json_and_declares_truncation():
    data={'snapshot':'a'*32,'tree':[{'ref':f'e{i}','role':'textbox','name':'n'*160} for i in range(1,151)]}
    compact=compact_browser_observation(json.dumps(data))
    result=json.loads(compact)
    assert result['truncated'] and 0<len(result['controls'])<150 and len(compact)<6000


def test_non_inspection_text_does_not_become_a_browser_snapshot():
    assert compact_browser_observation('not JSON') is None
    assert compact_browser_observation('[1,2]') is None


def test_targets_are_retained_whole_but_navigation_invalidates_prior_page_refs():
    targets=compact_browser_targets('links',json.dumps([{'text':'Arquivo','href':'https://example.test/file.txt'}]))
    observation=json.dumps({'snapshot':'a'*32,'controls':[{'ref':'e8','role':'textbox'}]})
    steps=[{'tool':'browser','ok':True,'params':{'action':'inspect'},'browser_observation':observation},
           {'tool':'browser','ok':True,'params':{'action':'links'},'browser_targets':targets},
           {'tool':'browser','ok':True,'params':{'action':'tabs'},'browser_targets':{'tabs':[{'id':'t1'}]}}]
    assert browser_planning_state(steps)['links'][0]['href'].endswith('/file.txt')
    assert browser_planning_state(steps)['snapshot']=='a'*32
    steps.append({'tool':'browser','ok':True,'params':{'action':'click'}})
    assert browser_planning_state(steps)=={'tabs':[{'id':'t1'}]}


def test_switching_does_not_rewrite_the_historical_tab_observation():
    original=[{'id':'t1','active':False},{'id':'t2','active':True}]
    steps=[{'tool':'browser','ok':True,'params':{'action':'tabs'},'browser_targets':{'tabs':original}},
           {'tool':'browser','ok':True,'verified':True,'params':{'action':'switch_tab','tab_id':'t1'}}]
    state=browser_planning_state(steps)
    assert state['tabs'][0]['active'] and not state['tabs'][1]['active']
    assert original==[{'id':'t1','active':False},{'id':'t2','active':True}]
