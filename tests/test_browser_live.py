"""Opt-in real Chromium tests against our own disposable HTTP fixture.

NYX_TEST_BROWSER=1 python -m pytest tests/test_browser_live.py
No personal profiles, external sites, generated programs or account actions.
"""
import http.server
import os
import threading
import time

import pytest

from core.operation_control import OperationCancelled
from tools.browser_tool import BrowserError, BrowserSession

pytestmark = pytest.mark.skipif(os.environ.get("NYX_TEST_BROWSER") != "1", reason="real browser opt-in")

PAGE = b'''<!doctype html><meta charset="utf-8"><title>Nyx live fixture</title>
<label for="input">Nome</label><input id="input" value="old">
<button id="go">Enviar</button><output id="result">pending</output>
<button disabled id="disabled">Disabled</button>
<button class="duplicate">Duplicate</button><button class="duplicate">Duplicate</button>
<button id="covered" style="position:absolute;left:700px;top:200px">Covered</button>
<div style="position:absolute;left:690px;top:190px;width:160px;height:90px;background:black"></div>
<button id="hidden" style="display:none">Hidden</button>
<script>
window.trustedInput=false; window.trustedClick=false;
document.querySelector('#input').addEventListener('input', e => window.trustedInput=e.isTrusted);
document.querySelector('#go').addEventListener('click', e => {
 window.trustedClick=e.isTrusted;
 setTimeout(() => document.querySelector('#result').textContent='Hello '+document.querySelector('#input').value,100);
});
</script>'''


@pytest.fixture(scope="module")
def browser():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/destination")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path == "/slow":
                time.sleep(0.4)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    session = BrowserSession(timeout=8)
    try:
        yield session, f"http://127.0.0.1:{server.server_port}"
    finally:
        session.control.resume()
        session.close()
        server.shutdown()
        server.server_close()


def test_real_input_dynamic_result_and_unicode(browser):
    session, url = browser
    session.open(url)
    session.type_text({"label": "Nome"}, "Nyx ação 🌙")
    session.click({"role": "button", "name": "Enviar"})
    assert session.wait_for_text("Hello Nyx ação 🌙", timeout=2)
    assert session._evaluate("window.trustedInput && window.trustedClick") is True
    session.type_text("#input", "")
    assert session._evaluate("document.querySelector('#input').value") == ""


@pytest.mark.parametrize("selector", ["#disabled", ".duplicate", "#hidden", "#covered", "#missing"])
def test_rejects_unactionable_targets(browser, selector):
    session, _ = browser
    with pytest.raises(BrowserError):
        session.click(selector)


def test_navigation_waits_for_new_document_and_follows_redirect(browser):
    session, url = browser
    session.open(url)
    started = time.monotonic()
    assert session.open(url + "/slow")["url"] == url + "/slow"
    assert time.monotonic() - started >= 0.35
    assert session.open(url + "/redirect")["url"] == url + "/destination"


def test_multiple_tabs_switch_and_close(browser):
    session, url = browser
    original = next(t["id"] for t in session.list_tabs() if t["active"])
    session.new_tab(url + "/second")
    new = next(t["id"] for t in session.list_tabs() if t["active"])
    assert new != original
    assert session.switch_tab(original)["url"].endswith("/destination")
    session.close_tab(new)
    assert new not in {t["id"] for t in session.list_tabs()}
    assert next(t["id"] for t in session.list_tabs() if t["active"]) == original
    with pytest.raises(BrowserError, match="sessão"):
        session.close_tab("../not-owned")


def test_wait_interrupts_and_latches_emergency(browser):
    session, _ = browser
    timer = threading.Timer(0.2, lambda: session.control.stop(emergency=True))
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(OperationCancelled):
            session.wait_for_text("never exists", timeout=10)
        assert time.monotonic() - started < 1.5
        with pytest.raises(OperationCancelled):
            session.control.begin()
    finally:
        timer.join()
        session.control.resume()
