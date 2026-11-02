"""The diagnostic's default path must report every real local HTTP scenario."""
import json
from pathlib import Path
import subprocess
import sys


def test_probe_default_completes_its_http_world_and_writes_all_outcomes(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'probe.json'
    completed = subprocess.run([sys.executable, str(root / 'tools' / 'verify_research_sources.py'),
                                '--runs', '1', '--output', str(output)], cwd=root,
                               capture_output=True, text=True, timeout=20)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    data = json.loads(output.read_text(encoding='utf-8'))
    assert data['runs'] == 1 and data['total'] == data['passed'] == 5
    assert {row['case'] for row in data['rows']} == {
        'http_article', 'http_empty', 'http_redirect', 'http_forbidden', 'http_binary'}
    assert data['http_fixture_requests']['/article'] == 2
    assert all(not row.get('source_url') or row['source_url'].startswith('<fixture>') for row in data['rows'])
