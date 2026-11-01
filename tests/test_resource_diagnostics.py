import time
from types import SimpleNamespace

from core import resource_diagnostics as diagnostics
from core.runtime_budget import GIB, ResourceSnapshot


def test_process_inspection_only_on_explicit_request(monkeypatch):
    monkeypatch.setattr(diagnostics, 'resource_snapshot', lambda: ResourceSnapshot(2*GIB, 12*GIB, 8*GIB))
    monkeypatch.setattr(diagnostics, 'memory_consumers', lambda: (_ for _ in ()).throw(AssertionError('Unexpected enumeration')))
    report = diagnostics.diagnose_resources()
    assert report['consumers'] is None and not report['processes_requested']
    assert not report['critical_pressure']


def test_process_groups_sum_working_sets_without_paths_or_control_characters(monkeypatch):
    import psutil
    class Process:
        def __init__(self, name, size):
            self.info = {'name': name, 'memory_info': SimpleNamespace(rss=size)}
    def enumerate_processes(attrs, ad_value):
        assert attrs == ['name', 'memory_info'] and ad_value is None
        return iter([Process('Editor.exe', 100), Process('editor.exe', 200),
                     Process('C:\\private\\Other\n.exe', 500), Process(None, 600)])
    monkeypatch.setattr(psutil, 'process_iter', enumerate_processes)
    report = diagnostics.memory_consumers()
    assert report['rows'] == [{'name': 'Other.exe', 'processes': 1, 'rss_bytes': 500},
                              {'name': 'Editor.exe', 'processes': 2, 'rss_bytes': 300}]
    assert report['unavailable'] == 1


def test_process_inspection_supports_read_only_psutil_snapshot(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, 'process_iter', lambda *args, **kwargs: iter([
        SimpleNamespace(snapshot=SimpleNamespace(name='Editor', memory_info=SimpleNamespace(rss=1024)))
    ]))
    assert diagnostics.memory_consumers()['rows'][0]['rss_bytes'] == 1024


def test_process_enumeration_has_cooperative_budget(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, 'process_iter', lambda *args, **kwargs: iter([SimpleNamespace()]))
    report = diagnostics.memory_consumers(max_seconds=0)
    assert report['truncated'] and not report['rows']


def test_critical_refusal_has_actionable_navigation_and_safe_failure(monkeypatch):
    monkeypatch.setattr(diagnostics, 'resource_snapshot', lambda: ResourceSnapshot(GIB//2, 12*GIB, 8*GIB))
    def denied():
        raise PermissionError('private path not suitable for display')
    monkeypatch.setattr(diagnostics, 'memory_consumers', denied)
    report = diagnostics.diagnose_resources(True)
    assert report['critical_pressure']
    assert 'Diagnosticar memória' in report['reason']
    assert report['errors'] == ['Consulta de processos indisponível: PermissionError']


def test_dialog_collects_off_ui_thread_and_only_after_click(qapp, monkeypatch):
    from ui.resource_diagnostics import ResourceDiagnosticsDialog
    import threading
    ui_thread = threading.get_ident()
    requests = []
    def collect(include_processes):
        assert threading.get_ident() != ui_thread
        requests.append(include_processes)
        return {'resources': {'ram_available_bytes': 2*GIB, 'vram_free_bytes': 8*GIB},
                'reason': 'Medida', 'processes_requested': include_processes,
                'consumers': {'rows': [{'name': '<b>editor</b>', 'processes': 2, 'rss_bytes': GIB}],
                              'scanned': 2, 'unavailable': 0, 'truncated': True} if include_processes else None}
    monkeypatch.setattr(diagnostics, 'diagnose_resources', collect)
    dialog = ResourceDiagnosticsDialog()
    assert requests == []
    dialog.refresh_button.click()
    deadline = time.monotonic() + 3
    while dialog.worker is not None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.001)
    assert requests == [False] and dialog.table.rowCount() == 0
    dialog.process_button.click()
    deadline = time.monotonic() + 3
    while dialog.worker is not None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.001)
    assert requests == [False, True] and dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == '<b>editor</b>'
    assert 'Consulta parcial' in dialog.summary.text()
    assert dialog.pool.waitForDone(1000)
    dialog.close()
