"""Independent CDP reader: does not import Nyx tools, locators or verifiers."""
import hashlib
import json
import re
import time
import urllib.request
from contextlib import closing

import websocket

_CLAUSE_BREAK = re.compile(r'[.!?;\n]+|,?\s+\b(?:mas|porém|contudo|entretanto)\b\s*', re.I)
_UNCERTAIN = re.compile(
    r'\b(?:não|nao|nem|sem|talvez|possivelmente|provavelmente|poderia|parece|'
    r'incert[oa]|incerteza|duvido|suponho|acho|imagino|hipótese|hipotese)\b|'
    r'\b(?:falta|precis[oa]|necessário|necessario)\s+(?:ainda\s+)?(?:ler|confirmar|verificar)', re.I)
_CODE_ASSERTION = re.compile(
    r'\bc[oó]digo\b(?:\s+[^\n.!?;:]{0,90}?)?\s+(?:é|eh|vale|corresponde a|encontrado foi)\s+\S|'
    r'\bc[oó]digo\b[^\n.!?;:]{0,90}:\s*\S|'
    r'\bc[oó]digo\s+[\"\'`*]*[0-9]+\b', re.I)


def _assertive_clauses(speech):
    """Conservative Portuguese claim detector, not a universal truth classifier.

    Keep negation local: a failed click in one sentence does not excuse a wrong
    code asserted in the next. Questions and explicitly uncertain statements
    are not claims of completion. External page text is never evaluated as code.
    """
    for sentence in re.findall(r'[^.!?;\n]+(?:[.!?;\n]+|$)', str(speech)):
        if sentence.rstrip().endswith('?'):
            continue
        for raw in _CLAUSE_BREAK.split(sentence):
            clause = raw.strip().casefold()
            if clause and not _UNCERTAIN.search(clause) and not re.search(r'\b(?:se|caso|quando)\b', clause):
                yield clause


def asserts_value(speech, value):
    """Require an exact scalar in an affirmative clause, not a substring."""
    pattern = re.compile(r'(?<!\w)' + re.escape(str(value).casefold()) + r'(?!\w)')
    return any(pattern.search(clause) for clause in _assertive_clauses(speech))


WORLD = r"""(() => {
 const frame=document.querySelector('iframe');const shadow=document.querySelector('#widget')?.shadowRoot;
 const audio=document.querySelector('audio');
 return {url:location.href,title:document.title,visible:document.visibilityState,
 text:(document.body?.innerText||'').slice(0,16000),
 fields:Array.from(document.querySelectorAll('input')).map(e=>({id:e.id,value:e.value})),
 table:Array.from(document.querySelectorAll('tbody tr')).map(tr=>Array.from(tr.cells).map(c=>c.textContent)),
 frameValue:frame?.contentDocument?.querySelector('input')?.value,
 frameTrusted:frame?.contentWindow?.trustedInput,
 shadowValue:shadow?.querySelector('input')?.value,shadowTrusted:window.trustedInput,
 media:audio?{time:audio.currentTime,paused:audio.paused,ended:audio.ended,ready:audio.readyState}:null};
})()"""


class BrowserObserver:
    def __init__(self, port):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Porta local de observação inválida.')
        self.port, self.sequence = port, 0

    def pages(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json/list', timeout=3) as response:
            targets = json.loads(response.read(1_048_577))
        return [target for target in targets if target.get('type')=='page'][:20]

    def evaluate(self, target):
        endpoint = target.get('webSocketDebuggerUrl','')
        if not endpoint.startswith(f'ws://127.0.0.1:{self.port}/') and not endpoint.startswith(f'ws://localhost:{self.port}/'):
            raise ValueError('Endpoint não pertence ao navegador observado.')
        self.sequence += 1
        with closing(websocket.create_connection(endpoint,timeout=3,suppress_origin=True)) as transport:
            transport.send(json.dumps({'id':self.sequence,'method':'Runtime.evaluate',
                'params':{'expression':WORLD,'returnByValue':True}}))
            deadline = time.monotonic()+3
            while time.monotonic()<deadline:
                raw = transport.recv()
                if len(raw)>1_048_576:
                    raise ValueError('Observação excede o limite.')
                packet = json.loads(raw)
                if packet.get('id')==self.sequence:
                    if packet.get('error') or packet.get('result',{}).get('exceptionDetails'):
                        raise ValueError('Leitura independente recusada.')
                    return packet['result']['result'].get('value',{})
            raise TimeoutError('Observação CDP não respondeu.')

    def snapshot(self):
        return [self.evaluate(target) for target in self.pages()]


def verify_fixture(fixture, observations, speech, path, media_samples, *, restarted):
    number, code, value = fixture.number, fixture.code, fixture.value
    pages = [page for page in observations if page.get('url','').startswith(fixture.base+'/')]
    current = next((page for page in pages if page.get('visible')=='visible'), pages[0] if pages else {})
    text = current.get('text','')
    detail = {}
    if number == 1:
        ok = current.get('url')==fixture.base+'/' and code in text and asserts_value(speech,code)
    elif number == 2:
        searched = any(row['query'].get('q')==['Nyx'] for row in fixture.requests)
        ok = searched and current.get('url')==fixture.base+'/result/2' and asserts_value(speech,code)
        detail = {'search_request_observed':searched,'second_result_observed':current.get('url','').endswith('/result/2')}
    elif number == 3:
        expected = [['Saturno',code],['Vênus',str(int(code)+19)]]
        answer_exact = all(asserts_value(speech,item) for row in expected for item in row)
        ok = current.get('table')==expected and answer_exact
        detail = {'table_exact':current.get('table')==expected,'answer_values_present':answer_exact}
    elif number == 4:
        expected = {'name':value,'message':'Olá mundo','trusted':True}
        ok = expected in fixture.events and 'Cadastro local salvo' in text
        detail = {'trusted_submission':expected in fixture.events,'server_events':len(fixture.events)}
    elif number == 5:
        ok = current.get('frameValue')==value and current.get('frameTrusted') is True
        detail = {'field_exact':current.get('frameValue')==value,'trusted_input':current.get('frameTrusted') is True}
    elif number == 6:
        ok = current.get('shadowValue')==value and current.get('shadowTrusted') is True
        detail = {'field_exact':current.get('shadowValue')==value,'trusted_input':current.get('shadowTrusted') is True}
    elif number == 7:
        ok = current.get('url')==fixture.base+'/tab/origin' and current.get('visible')=='visible' and asserts_value(speech,code)
        detail = {'origin_tab_visible':current.get('url')==fixture.base+'/tab/origin' and current.get('visible')=='visible'}
    elif number == 8:
        actual = path.read_bytes() if path.is_file() else None
        ok = actual == fixture.file_bytes
        detail = {'file_exact':ok,'bytes':len(actual) if actual is not None else 0,
                  'sha256_matches':actual is not None and hashlib.sha256(actual).digest()==hashlib.sha256(fixture.file_bytes).digest()}
    elif number == 9:
        running = [sample for sample in media_samples if not sample.get('paused',True) and sample.get('ready',0)>=2]
        advanced = len(running)>1 and max(s['time'] for s in running)-min(s['time'] for s in running)>.15
        paused = bool(current.get('media') and current['media']['paused'] and current['media']['time']>.15)
        ok = advanced and paused and bool(re.search(r'pausad|parad',speech,re.I))
        detail = {'time_advanced_independently':advanced,'finally_paused':paused,'samples':len(media_samples)}
    elif number == 10:
        persisted = any(row['path']=='/session' and row['session_present'] for row in fixture.requests)
        ok = restarted and persisted and 'Sessão local de teste ativa' in text and bool(re.search(r'ativ|persist|mantid',speech,re.I))
        detail = {'browser_restarted':restarted,'server_received_persistent_session':persisted}
    else:
        raise ValueError('Cenário desconhecido; verificador não pode aprovar.')
    return {'ok':bool(ok),'check':'Independent CDP DOM/visibility + HTTP fixture state + bytes on disk',
            'details':detail,'observed_pages':len(pages)}


def claims_completion(speech):
    for clause in _assertive_clauses(speech):
        if _CODE_ASSERTION.search(clause):
            return True
        if re.search(r'\b(?:abri|preenchi|salvei|baixei|conclu[ií]|reproduzi|pausei|verifiquei)\b',clause):
            return True
        if re.search(r'\b(?:pedido|tarefa|download|cadastro|formulário)\b[^.!?\n]{0,50}\bconclu[ií]d[oa]\b',clause):
            return True
    return False
