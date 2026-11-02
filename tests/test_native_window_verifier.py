import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from bench.native_windows import APPS, matches  # noqa: E402


def test_uia_or_title_success_does_not_replace_independent_process_identity():
    assert matches({'process':'CalculatorApp.exe','title':'test'},APPS['calculator'])
    assert not matches({'process':'ApplicationFrameHost.exe','title':'Calculadora'},APPS['calculator'])
    assert matches({'process':'ApplicationFrameHost.exe','title':'Calculadora',
                    'child_processes':['CalculatorApp.exe']},APPS['calculator'])
    assert not matches({'process':'ApplicationFrameHost.exe','title':'Outro aplicativo'},APPS['calculator'])
    assert not matches({'process':'Editor.exe','title':'Calculadora'},APPS['calculator'])
    assert not matches({'process':'ApplicationFrameHost.exe','title':'Calculadora.png - Fotos'},APPS['calculator'])


def test_explorer_desktop_shell_does_not_count_as_a_file_window():
    window = {'process':'explorer.exe', 'title':'Program Manager', 'class':'Progman'}
    assert not matches(window, APPS['explorer'])
    window.update(title='Fixture', **{'class':'CabinetWClass'})
    assert matches(window, APPS['explorer'])


def test_native_bench_preserves_child_resource_failure_instead_of_only_exit_code(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from bench.catalog import cases
    from bench import native_suite
    def child(command, **kwargs):
        report = Path(command[command.index('--output')+1])
        report.write_text(json.dumps({'rows':[], 'runtime_failure':{
            'error_code':'RESOURCE_PRESSURE', 'error':'RAM livre insuficiente; nenhuma geração enviada.'}}))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(native_suite.subprocess, 'run', child)
    monkeypatch.setattr(native_suite, 'precheck_running', lambda keys:[])
    selected = [case for case in cases() if case.id == 'apps-01']
    rows = native_suite.run_native_cases(tmp_path, selected, 3, 'fixture', 'normal', tmp_path)
    assert len(rows) == 3 and all(row['status']=='BLOCKED_RUNTIME' for row in rows)
    assert all(row['error_code']=='RESOURCE_PRESSURE' and 'nenhuma geração' in row['error'] for row in rows)
