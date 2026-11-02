"""Real CDP against disposable local Shadow DOM; no LLM or personal browser."""
import argparse
import http.server
import json
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'src')]

from tools.browser_tool import BrowserSession, make_browser_tool_func  # noqa: E402
from bench.environment import ResourceSampler  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture = (ROOT / 'bench/fixtures/shadow.html').read_bytes()
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(fixture)))
            self.end_headers()
            self.wfile.write(fixture)
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    session = BrowserSession(headless=True,persistent_profile=None,timeout=8)
    tool = make_browser_tool_func(session)
    report = {'scope': 'production CDP adapter, independent fixture state check, no LLM', 'rows': []}
    sampler = ResourceSampler()
    sampler.__enter__()
    try:
        for number in range(1, 4):
            session.open(f'http://127.0.0.1:{server.server_port}/{number}')
            started = time.monotonic()
            scope = ['#panel', '#nested']
            inspection = tool({'action': 'inspect', 'shadow': scope})
            typed = tool({'action': 'type', 'locator': {'shadow': scope, 'role': 'textbox', 'name': 'Nome da sombra'},
                          'text': 'Nyx ação 🌙'})
            clicked = tool({'action': 'click', 'locator': {'shadow': scope, 'role': 'button', 'name': 'Confirmar sombra'},
                            'expected_text': 'Hello Nyx ação 🌙', 'timeout': 1})
            observed = session._evaluate("""(() => ({text:document.querySelector('#result').textContent,
                external:document.querySelector('#name').value,
                trustedInput:window.trustedShadowInput, trustedClick:window.trustedShadowClick}))()""")
            passed = (inspection.ok and 'Nome da sombra' in inspection.output and 'fixture-secret-never-export' not in inspection.output
                      and typed.ok and typed.meta.get('verified') is True and clicked.ok
                      and observed == {'text': 'Hello Nyx ação 🌙', 'external': 'preservado', 'trustedInput': True, 'trustedClick': True})
            report['rows'].append({'iteration': number, 'elapsed_s': round(time.monotonic()-started, 3),
                                   'inspect_ok': inspection.ok, 'type_ok': typed.ok, 'click_ok': clicked.ok,
                                   'errors': [r.error for r in (inspection, typed, clicked) if not r.ok],
                                   'observed': observed, 'passed': passed})
        report['passed'] = all(row['passed'] for row in report['rows'])
    finally:
        sampler.__exit__(None,None,None)
        report['resources'] = sampler.report()
        session.close()
        server.shutdown()
        server.server_close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
