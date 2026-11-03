"""Constrain planning to complete browser actions, using only engine observations.

This guides generation. The browser still validates expiry, document identity,
permissions and postconditions at execution time; schema data grants no authority.
"""
import json
import re

from core.browser_context import PREFIX


def _object(properties, required):
    return {'type':'object','properties':properties,'required':required,'additionalProperties':False}


def browser_action_schema(history, goal=''):
    observation = {}
    for item in reversed(history or []):
        if item.get('nyx_browser_state') is True and str(item.get('content','')).startswith(PREFIX):
            try:
                observation = item.get('nyx_browser_state_data') or json.loads(item['content'][len(PREFIX):])
            except (ValueError, TypeError):
                pass
            break
    variants = []
    def action(name, fields=None, required=()):
        props = {'action':{'const':name}, **(fields or {})}
        variants.append(_object(props, ['action',*required]))
    text = {'type':'string','minLength':1}
    link_urls = sorted({row['href'] for row in observation.get('links',[]) if isinstance(row,dict)
                        and isinstance(row.get('href'),str) and re.match(r'^https?://',row['href'])})
    requested_urls = [value.rstrip('.,;)') for value in re.findall(r'https?://[^\s<>"\']+', goal)]
    allowed_urls = sorted(set(url.rstrip('.,;)') for url in requested_urls) | set(link_urls))
    url = {'enum':allowed_urls} if allowed_urls else {'type':'string','pattern':r'^https?://[^\s]+$'}
    tabs = observation.get('tabs',[])
    matching_tabs = [row for row in tabs if isinstance(row,dict) and row.get('title')
                     and str(row['title']).casefold() in goal.casefold()]
    desired_tab = matching_tabs[0] if len(matching_tabs)==1 else None
    page_ready = ((not requested_urls or bool(set(requested_urls) & set(observation.get('visited_urls',[]))))
                  and (not desired_tab or desired_tab.get('active') is True))
    for name in ('read','inspect','status','media_status','media_play','media_pause','tabs','links','tables'):
        if page_ready or name=='status' or (name=='tabs' and not desired_tab):
            action(name)
    existing_tab_goal = bool(re.search(r'\babas?\b',goal,re.I) and not requested_urls)
    if not existing_tab_goal:
        for name in ('open','new_tab'):
            action(name, {'url':url}, ('url',))
    tab_ids = [row['id'] for row in ([desired_tab] if desired_tab else tabs) if isinstance(row,dict) and isinstance(row.get('id'),str)]
    if tab_ids:
        action('switch_tab', {'tab_id':{'enum':tab_ids}}, ('tab_id',))
        action('close_tab', {'tab_id':{'enum':tab_ids}}, ('tab_id',))
    if link_urls:
        action('download', {'url':{'enum':link_urls},'path':text}, ('url','path'))
    action('wait_text', {'text':text}, ('text',))
    action('scroll', {'direction':{'enum':['up','down']},'amount':{'type':'integer','minimum':1,'maximum':3000}}, ('direction',))
    action('screenshot', {'path':text})
    action('close')
    controls = observation.get('controls', [])
    snapshot = observation.get('snapshot')
    from core.browser_fields import pending_fields
    pending = pending_fields(observation)
    if isinstance(snapshot,str) and len(snapshot)==32 and isinstance(controls,list):
        for name, roles, extra, required in (
            ('click', {'button','link','checkbox','radio','tab','menuitem','switch'},
             {}, ()),
            ('type', {'textbox','searchbox','spinbutton'},
             {'text':text,'submit':{'type':'boolean'},'expected_text':text}, ('text',)),
            ('select', {'combobox'}, {'value':text}, ('value',)),
            ('press', None, {'key':{'enum':['Enter','Tab','Escape','ArrowLeft','ArrowUp','ArrowRight',
                'ArrowDown','Home','End','PageUp','PageDown','Space','Ctrl+A']},'expected_text':text}, ('key',)),
            ('hover', None, {}, ()),
        ):
            if name=='type' and observation.get('bindings') and not pending:
                continue
            if pending and name in {'click','press','select','hover'}:
                continue
            refs = [entry['ref'] for entry in controls if isinstance(entry,dict)
                    and isinstance(entry.get('ref'),str) and not entry.get('protected')
                    and (roles is None or entry.get('role') in roles)]
            if refs:
                if name=='type' and pending:
                    for field in pending:
                        if field['ref'] in refs:
                            action(name, {'ref':{'const':field['ref']},'snapshot':{'const':snapshot},
                                'text':{'const':field['text']}}, ('ref','snapshot','text'))
                else:
                    action(name, {'ref':{'enum':refs}, 'snapshot':{'const':snapshot}, **extra},
                           ('ref','snapshot',*required))
    # The model chooses the action; avoid offering unrelated read-only detours
    # while explicit inputs or a requested download are still pending.
    field_goal = bool(re.search(r'\bpreencha\b',goal,re.I) or re.search(r'\bpesquise\b.{0,160}\bformulário\b',goal,re.I))
    if pending:
        allowed={'type','inspect','status'}
    elif field_goal and page_ready and not controls and not observation.get('typed_fields'):
        allowed={'inspect','status'}
    elif field_goal and observation.get('typed_fields'):
        submitted = any(item.get('role')=='button' for item in observation.get('clicked_controls',[]))
        saving_goal = bool(re.search(r'\b(?:salve|envie|salvar|enviar)\b',goal,re.I))
        if saving_goal and submitted:
            allowed=set() if observation.get('current_body') else {'read','wait_text','status'}
        elif not saving_goal and not re.search(r'\bpesquise\b',goal,re.I):
            allowed=set()
        else:
            allowed={'click','inspect','read','wait_text','status'}
    elif re.search(r'\b(?:baixe|baixar|download)\b',goal,re.I) and page_ready:
        allowed={'download','status'} if link_urls else {'links','status'}
    else:
        allowed=None
    if allowed is not None:
        variants=[variant for variant in variants if variant['properties']['action']['const'] in allowed]
    return _object({'type':{'const':'browser'},'params':{'anyOf':variants}}, ['type','params'])


def constrain_browser_schema(schema, names, history, goal=''):
    """Preserve the general contract for other tools; narrow only browser params."""
    others = [name for name in ['none',*names] if name!='browser']
    browser=browser_action_schema(history,goal)
    alternatives=[]
    if browser['properties']['params']['anyOf']:
        alternatives.append(browser)
    alternatives.append(_object({'type':{'enum':others},'params':{'type':'object'}}, ['type','params']))
    schema['properties']['action'] = {'anyOf':alternatives}
    return schema
