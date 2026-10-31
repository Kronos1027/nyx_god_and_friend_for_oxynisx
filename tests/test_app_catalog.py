from pathlib import Path
from types import SimpleNamespace

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
