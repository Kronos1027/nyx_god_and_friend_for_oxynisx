"""Real CDP, owned HTTP documents, independent fixture state; no personal profile."""
import http.server
import json
import os
from pathlib import Path
import threading

import pytest

from tools.browser_tool import BrowserError, BrowserSession, make_browser_tool_func

pytestmark = [pytest.mark.windows_live, pytest.mark.skipif(os.environ.get('NYX_TEST_BROWSER') != '1', reason='real browser opt-in')]

FRAME = b'''<!doctype html><title>Frame fixture</title><label for="f">Campo do frame</label><input id="f">
<button id="go">Confirmar frame</button><script>
window.typed=false;window.clicked=false;
document.querySelector('#f').oninput=e=>window.typed=e.isTrusted;
document.querySelector('#go').onclick=e=>window.clicked=e.isTrusted;
</script>'''
EXTRA = b'''<iframe id="child" title="Frame fixture" src="/frame" style="display:block;margin-top:60px;width:450px;height:180px"></iframe>
<label for="choose">Escolha</label><select id="choose"><option value="a">A</option><option value="disabled" disabled>Disabled</option><option value="b">B</option></select>
<button aria-label="Hover fixture" id="hover">Hover</button>
<input aria-label="Tecla fixture" id="key"><output id="key-result">pending</output>
<script>
window.trustedKey=false;window.trustedHover=false;window.trustedSelection=false;
document.querySelector('#choose').onchange=e=>window.trustedSelection=e.isTrusted;
document.querySelector('#hover').onmouseenter=e=>window.trustedHover=e.isTrusted;
document.querySelector('#key').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();window.trustedKey=e.isTrusted;document.querySelector('#key-result').textContent='Tecla confirmada';}};
</script>'''


@pytest.fixture(scope='module')
def ax_browser():
    main = (Path(__file__).resolve().parents[1]/'bench/fixtures/shadow.html').read_bytes()+EXTRA
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = FRAME if self.path == '/frame' else main
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    browser = BrowserSession(headless=True,persistent_profile=None,timeout=8)
    try:
        yield browser, f'http://127.0.0.1:{server.server_port}/'
    finally:
        browser.close()
        server.shutdown()
        server.server_close()


def reference(info, name, role):
    matches = [node for node in info['tree'] if node['name']==name and node['role']==role and node['actionable']]
    assert len(matches)==1, [(n['role'],n['name']) for n in info['tree']]
    return {'ref':matches[0]['ref'], 'snapshot':info['snapshot']}


@pytest.mark.parametrize('run', range(3))
def test_real_ax_refs_type_click_shadow_and_frame(ax_browser, run):
    browser, url = ax_browser
    browser.open(url+f'?run={run}')
    info = browser.inspect_page()
    assert info['tree'] and not info['frame_errors']
    assert 'fixture-secret-never-export' not in json.dumps(info)
    browser.type_text(reference(info,'Nome da sombra','textbox'), 'Nyx ação 🌙')
    browser.click(reference(info,'Confirmar sombra','button'))
    browser.type_text(reference(info,'Campo do frame','textbox'), 'Frame real')
    browser.click(reference(info,'Confirmar frame','button'))
    observed = browser._evaluate("""(() => ({result:document.querySelector('#result').textContent,
        external:document.querySelector('#name').value,shadowInput:window.trustedShadowInput,
        shadowClick:window.trustedShadowClick,frameInput:document.querySelector('#child').contentWindow.typed,
        frameClick:document.querySelector('#child').contentWindow.clicked,
        frameValue:document.querySelector('#child').contentDocument.querySelector('#f').value}))()""")
    assert observed == {'result':'Hello Nyx ação 🌙','external':'preservado','shadowInput':True,'shadowClick':True,
                        'frameInput':True,'frameClick':True,'frameValue':'Frame real'}


@pytest.mark.parametrize('locator', [
    {'shadow':['#panel','#nested'],'css':'#disabled'},
    {'shadow':['#panel','#nested'],'css':'.duplicate'},
    {'shadow':['#panel','#nested'],'css':'#hidden'},
    {'shadow':['#panel','#nested'],'css':'#covered'},
    {'shadow':['#closed'],'css':'input'},
    {'shadow':['.ambiguous-host'],'css':'input'},
])
def test_shadow_negative_cases_never_dispatch(ax_browser, locator):
    browser, url = ax_browser
    browser.open(url)
    with pytest.raises(BrowserError):
        browser.click(locator)
    assert browser._evaluate('window.trustedShadowClick') is False


def test_refs_expire_on_navigation_replacement_and_reinspection(ax_browser):
    browser, url = ax_browser
    browser.open(url)
    info = browser.inspect_page()
    old = reference(info,'Confirmar sombra','button')
    browser._evaluate("document.querySelector('#panel').shadowRoot.querySelector('#nested').shadowRoot.querySelector('#go').setAttribute('aria-label','Changed')")
    with pytest.raises(BrowserError) as changed:
        browser.click(old)
    assert changed.value.code == 'ELEMENT_STALE'
    assert not browser._evaluate('window.trustedShadowClick')
    refreshed = browser.inspect_page()
    with pytest.raises(BrowserError, match='antiga'):
        browser.click(old)
    current = reference(refreshed,'Changed','button')
    browser.open(url)
    with pytest.raises(BrowserError) as navigated:
        browser.click(current)
    assert navigated.value.code == 'ELEMENT_STALE'
    assert not browser._evaluate('window.trustedShadowClick')


def test_password_refs_and_scoped_password_typing_are_blocked(ax_browser):
    browser, url = ax_browser
    browser.open(url)
    info = browser.inspect_page()
    protected = next(node for node in info['tree'] if node['protected'])
    with pytest.raises(BrowserError) as password:
        browser.type_text({'ref':protected['ref'],'snapshot':info['snapshot']}, 'forbidden')
    assert password.value.code == 'PERMISSION'
    result = make_browser_tool_func(browser)({'action':'type',
        'locator':{'shadow':['#panel','#nested'],'css':'#secret'},'text':'forbidden'})
    assert not result.ok
    assert result.meta['error_code'] == 'PERMISSION'


@pytest.mark.parametrize('run', range(3))
def test_select_hover_and_press_by_refs_are_real_and_verified_conservatively(ax_browser, run):
    from core.verifier import ActionVerifier
    browser, url = ax_browser
    browser.open(url+f'?actions={run}')
    info = browser.inspect_page()
    tool = make_browser_tool_func(browser)
    selected = tool({'action':'select', **reference(info,'Escolha','combobox'), 'value':'b'})
    assert selected.ok and selected.meta['verified']
    hovered = tool({'action':'hover', **reference(info,'Hover fixture','button')})
    assert hovered.ok and hovered.meta['verified']
    typed = tool({'action':'type', **reference(info,'Tecla fixture','textbox'), 'text':'real','submit':True})
    assert typed.ok and typed.meta['field_verified'] and not typed.meta['verified']
    assert not ActionVerifier().verify('browser', {'action':'type'}, typed).verified
    pressed = tool({'action':'press', **reference(info,'Tecla fixture','textbox'), 'key':'Enter','expected_text':'Tecla confirmada'})
    assert pressed.ok and pressed.meta['verified']
    observed = browser._evaluate("""({value:document.querySelector('#choose').value,
        field:document.querySelector('#key').value,selection:window.trustedSelection,
        hover:window.trustedHover,key:window.trustedKey})""")
    assert observed == {'value':'b','field':'real','selection':True,'hover':True,'key':True}


def test_select_ambiguity_disabled_and_invalid_key_do_not_mutate(ax_browser):
    browser, url = ax_browser
    browser.open(url)
    browser._evaluate("document.querySelector('#choose').insertAdjacentHTML('beforeend','<option value=a>Duplicate</option>')")
    info = browser.inspect_page()
    for value in ('a','disabled','absent'):
        with pytest.raises(BrowserError):
            browser.select(reference(info,'Escolha','combobox'),value)
    with pytest.raises(BrowserError):
        browser.press(reference(info,'Tecla fixture','textbox'), 'Ctrl+Shift+J')
    assert browser._evaluate('window.trustedSelection || window.trustedKey') is False
