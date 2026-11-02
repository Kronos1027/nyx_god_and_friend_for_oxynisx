import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bench.catalog import cases  # noqa: E402
from bench import app_inventory  # noqa: E402
from bench.reporting import summarize  # noqa: E402


def test_app_denominator_contains_only_independently_installed_targets():
    catalog = [case for case in cases() if case.category=='apps']
    apps = {key:{'installed':False} for key in app_inventory.APPS}
    apps['calculator']['installed'] = True
    apps['vscode']['installed'] = True
    apps['steam']['installed'] = None
    selected, excluded = app_inventory.installed_cases(catalog,{'complete':False,'apps':apps})
    assert [(case.id,case.target) for case in selected] == [('apps-01','calculator'),('apps-11','vscode')]
    assert next(row for row in excluded if row['id']=='apps-09')['reason'] == 'INVENTORY_UNKNOWN'
    assert next(row for row in excluded if row['id']=='apps-03')['reason'] == 'NOT_INSTALLED'


def test_precheck_never_closes_preexisting_process_and_ignores_desktop_shell(monkeypatch):
    monkeypatch.setattr(app_inventory,'visible_windows',lambda:[])
    monkeypatch.setattr('psutil.process_iter',lambda attrs:iter([
        SimpleNamespace(info={'name':'explorer.exe'}),SimpleNamespace(info={'name':'Steam.exe'})]))
    blocked = app_inventory.precheck_running(['explorer','steam'])
    assert [row['app'] for row in blocked] == ['steam']
    assert blocked[0]['error_code']=='PRECHECK_CLOSE_APP' and 'Feche' in blocked[0]['message']


def test_environment_block_is_not_counted_as_executed_or_focus_failure():
    rows = [{'category':'apps','run':run,'status':'BLOCKED_ENVIRONMENT','ok':False,
             'false_success':False,'elapsed_s':0} for run in range(1,4)]
    summary = summarize(rows,3)['apps']
    assert summary['blocked_environment']==3 and summary['executed']==0
    assert summary['focus_measured']==0 and not summary['category_gate_passed']
