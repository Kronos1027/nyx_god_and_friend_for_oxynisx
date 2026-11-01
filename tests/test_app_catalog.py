from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from tools import app_catalog
from tools.installed_apps import InstalledApp


def test_package_launch_requires_registration_and_safe_identity(monkeypatch):
    calls = []
    monkeypatch.setattr(app_catalog, 'packaged_apps', lambda: [('Calculadora', 'Vendor.Package_123!App')])
    monkeypatch.setattr(app_catalog.subprocess, 'Popen', lambda args, **kwargs: calls.append(args))
    for appid in ('Vendor.Package_123!App & calc', 'Unknown.Package_123!App', '../bad'):
        with pytest.raises(ValueError):
            app_catalog.launch_package(InstalledApp('Calculadora', Path('C:/Windows/explorer.exe'), 'fixture', appid))
    assert calls == []
    app_catalog.launch_package(InstalledApp('Calculadora', Path('C:/Windows/explorer.exe'), 'fixture', 'Vendor.Package_123!App'))
    assert calls == [[str(Path('C:/Windows/explorer.exe')), 'shell:AppsFolder\\Vendor.Package_123!App']]


def test_package_catalog_filters_non_package_ids_and_caches(monkeypatch):
    calls = []
    def read(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=b'[{"Name":"Calc","AppID":"Vendor.Package_123!App"},{"Name":"Bad","AppID":"evil & calc"}]')
    monkeypatch.setattr(app_catalog, '_expires', 0)
    monkeypatch.setattr(app_catalog, '_cached', ())
    monkeypatch.setattr(app_catalog.subprocess, 'run', read)
    assert app_catalog.packaged_apps() == [('Calc', 'Vendor.Package_123!App')]
    assert app_catalog.packaged_apps() == [('Calc', 'Vendor.Package_123!App')]
    assert len(calls) == 1


def test_explorer_resolution_cannot_resolve_to_an_arbitrary_packaged_app(monkeypatch):
    from tools import installed_apps
    explorer = InstalledApp('Explorador de Arquivos', Path('C:/Windows/explorer.exe'), 'Windows')
    package = InstalledApp('Calculadora', explorer.path, 'Windows AppsFolder', 'Vendor.Package_123!App')
    monkeypatch.setattr(installed_apps, 'installed_apps', lambda: [package, explorer])
    assert installed_apps.resolve_app('explorador') == explorer
    assert installed_apps.resolve_app('calculadora') == package


@pytest.mark.parametrize('status,cloaked,expected', [(0,0,True), (0,2,False), (-1,0,None)])
def test_dwm_visibility_never_accepts_cloaked_or_unobserved_window(monkeypatch, status, cloaked, expected):
    class Query:
        def __call__(self, hwnd, attribute, output, size):
            assert hwnd == 42 and attribute == 14
            output._obj.value = cloaked
            return status
    monkeypatch.setattr(app_catalog.ctypes, 'WinDLL', lambda *a, **k: SimpleNamespace(DwmGetWindowAttribute=Query()), raising=False)
    if expected is None:
        with pytest.raises(OSError, match='visibilidade DWM'):
            app_catalog.window_is_uncloaked(42)
    else:
        assert app_catalog.window_is_uncloaked(42) == expected


def test_uwp_uses_visible_host_with_owned_child_not_cloaked_core(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pygetwindow', SimpleNamespace(getAllWindows=lambda: [
        SimpleNamespace(visible=True, title='Calculator', _hWnd=10),
        SimpleNamespace(visible=True, title='Calculator', _hWnd=50)]))
    monkeypatch.setitem(sys.modules, 'pywintypes', SimpleNamespace(error=OSError))
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(
        EnumChildWindows=lambda hwnd, callback, unused: callback(51, unused)))
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(
        GetWindowThreadProcessId=lambda hwnd: (1, 7 if hwnd == 50 else 22)))
    monkeypatch.setattr('psutil.Process', lambda pid: SimpleNamespace(create_time=lambda:100, is_running=lambda:True))
    monkeypatch.setattr(app_catalog, 'process_app_id', lambda pid:'Vendor.Package!App' if pid==22 else None)
    monkeypatch.setattr(app_catalog, 'window_is_uncloaked', lambda hwnd:hwnd==50)
    assert app_catalog.matching_package_windows('Vendor.Package!App') == [
        {'hwnd':50, 'pid':22, 'created':100, 'owner':'registered_app_user_model_id'}]
