from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from tools import installed_apps as apps
from tools.ui_tool import UITool
from core.verifier import ActionVerifier
from tools.registry import ToolResult


def test_installed_name_resolution_never_falls_back_to_cwd(tmp_path, monkeypatch):
    registered = tmp_path / "installed" / "steam.exe"
    registered.parent.mkdir()
    registered.write_bytes(b"fixture")
    (tmp_path / "steam.exe").write_bytes(b"untrusted cwd")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(apps, "installed_apps", lambda: [apps.InstalledApp("Steam", registered, "fixture")])
    assert apps.resolve_app("steam.exe").path == registered
    assert apps.resolve_app("STEAM").path == registered
    for value in ("steam.exe --argument", "steam & calc", "script.ps1", str(tmp_path / "steam.exe")):
        with pytest.raises(ValueError):
            apps.resolve_app(value)


def test_ambiguous_installed_name_requires_discovery(monkeypatch):
    monkeypatch.setattr(apps, "installed_apps", lambda: [
        apps.InstalledApp("Editor", Path("C:/One/editor.exe"), "fixture"),
        apps.InstalledApp("Editor", Path("C:/Two/editor.exe"), "fixture")])
    with pytest.raises(ValueError, match="ambíguo"):
        apps.resolve_app("Editor")


@pytest.mark.parametrize("key", ["app", "name", "app_name", "path"])
def test_open_installed_app_alias_and_verified_window(key, tmp_path, monkeypatch):
    app = apps.InstalledApp("Steam", tmp_path / "steam.exe", "fixture")
    monkeypatch.setattr(apps, "resolve_app", lambda name: app if name == "Steam" else pytest.fail(name))
    observations = iter([[], [{"hwnd": 42, "title": "Steam", "pid": 123}]])
    monkeypatch.setattr(apps, "matching_windows", lambda path: next(observations))
    opened = []
    monkeypatch.setattr("os.startfile", opened.append)
    result = UITool(tmp_path / "shots").open_app({key: "Steam"})
    assert opened == [str(app.path)] and result.ok and result.meta["verified"]
    assert ActionVerifier().verify("ui_action", {"action": "open_app"}, result).verified


def test_cancel_after_dispatch_preserves_unknown_outcome(tmp_path, monkeypatch):
    app = apps.InstalledApp("Steam", tmp_path / "steam.exe", "fixture")
    tool = UITool(tmp_path / "shots")
    monkeypatch.setattr(apps, "resolve_app", lambda name: app)
    monkeypatch.setattr(apps, "matching_windows", lambda path: [])
    monkeypatch.setattr("os.startfile", lambda path: tool.control.stop())
    result = tool.open_app({"app": "Steam"})
    assert not result.ok and result.meta["outcome_unknown"]


def test_installed_app_verification_never_uses_unrelated_title(monkeypatch):
    monkeypatch.setattr("pygetwindow.getAllTitles", lambda: ["Steam — unrelated document"])
    result = ToolResult(True, "abertura solicitada", meta={"check": "installed_app_window", "verified": False, "windows": []})
    assert not ActionVerifier().verify("ui_action", {"action": "open_app", "app": "Steam"}, result).verified


def test_window_list_counts_observed_windows():
    result = ToolResult(True, "windows", meta={"windows": [{"title": "One"}, {"title": "Two"}]})
    assert "2 itens" in ActionVerifier().verify("ui_action", {"action": "list_windows"}, result).details


class ProcessFixture:
    def __init__(self, pid, path, parent=None, created=10, running=True):
        self.pid, self.path, self.ancestor = pid, path, parent
        self.created, self.running = created, running

    def exe(self):
        return str(self.path)

    def parent(self):
        return self.ancestor

    def create_time(self):
        return self.created

    def is_running(self):
        return self.running


def test_steam_helper_requires_installed_path_and_live_client_ancestor(tmp_path):
    executable = tmp_path / 'Steam' / 'steam.exe'
    client = ProcessFixture(1, executable)
    helper = ProcessFixture(2, executable.parent / 'bin' / 'cef' / 'steamwebhelper.exe', client, created=20)
    assert apps._matching_owner(helper, executable) == 'steam_renderer_with_client_ancestor'
    assert apps._matching_owner(client, executable) == 'executable'
    for candidate in (
        ProcessFixture(3, tmp_path / 'unrelated' / 'steamwebhelper.exe', client, created=20),
        ProcessFixture(4, executable.parent / 'steamapps' / 'game.exe', client, created=20),
        ProcessFixture(5, helper.path, created=20),
        ProcessFixture(6, helper.path, ProcessFixture(7, executable, created=30), created=20),
        ProcessFixture(8, helper.path, ProcessFixture(9, executable, running=False), created=20),
    ):
        assert apps._matching_owner(candidate, executable) is None


def test_matching_window_rejects_reused_hwnd(tmp_path, monkeypatch):
    executable = tmp_path / 'steam.exe'
    process = ProcessFixture(2, executable)
    monkeypatch.setattr('pygetwindow.getAllWindows', lambda: [SimpleNamespace(visible=True, title='Steam', _hWnd=1)])
    monkeypatch.setattr('psutil.Process', lambda pid: process)
    pids = iter([(0, 2), (0, 3)])
    monkeypatch.setattr('win32process.GetWindowThreadProcessId', lambda hwnd: next(pids))
    assert apps.matching_windows(executable) == []


@pytest.mark.parametrize('alias', ['query', 'app', 'name', 'app_name'])
def test_installed_apps_filter_alias_does_not_return_unrelated_apps(tmp_path, monkeypatch, alias):
    monkeypatch.setattr(apps, 'installed_apps', lambda: [
        apps.InstalledApp('Steam', tmp_path / 'steam.exe', 'fixture'),
        apps.InstalledApp('Editor', tmp_path / 'editor.exe', 'fixture')])
    result = UITool(tmp_path / 'shots').list_installed_apps({alias: 'Steam'})
    assert json.loads(result.output)['names'] == ['Steam']
    assert len(result.meta['apps']) == 1
    assert str(tmp_path) not in result.output


def steam_fixture(tmp_path, monkeypatch):
    steam = tmp_path / 'Steam'
    library = tmp_path / 'Library'
    (steam / 'steamapps').mkdir(parents=True)
    (library / 'steamapps' / 'common').mkdir(parents=True)
    monkeypatch.setattr(apps, 'resolve_app', lambda name: apps.InstalledApp('Steam', steam / 'steam.exe', 'fixture'))
    escaped = str(library).replace('\\', '\\\\')
    (steam / 'steamapps' / 'libraryfolders.vdf').write_text(
        '"libraryfolders" { "1" { "path" "' + escaped + '" "apps" { "42" "12" } } }', encoding='utf-8')
    return steam, library


def write_manifest(library, appid, name, directory, flags='4', *, create_directory=True):
    (library / 'steamapps' / f'appmanifest_{appid}.acf').write_text(
        '"AppState" { "appid" "' + appid + '" "name" "' + name + '" "installdir" "'
        + directory + '" "StateFlags" "' + flags + '" }', encoding='utf-8')
    if create_directory:
        (library / 'steamapps' / 'common' / directory).mkdir(parents=True, exist_ok=True)


def test_steam_manifests_show_installed_games_without_launching(tmp_path, monkeypatch):
    _, library = steam_fixture(tmp_path, monkeypatch)
    write_manifest(library, '42', 'Jogo A', 'GameA')
    write_manifest(library, '43', 'Jogo B', 'GameB', '6')
    write_manifest(library, '44', 'Steam Linux Runtime 3.0', 'runtime')
    write_manifest(library, '45', 'Incompleto', 'incomplete', '2')
    write_manifest(library, '46', 'Removido', 'deleted', create_directory=False)
    monkeypatch.setattr('os.startfile', lambda *args: pytest.fail('Catalog must not launch anything'))
    result = UITool(tmp_path / 'shots').run({'action': 'list_steam_games'})
    assert result.ok
    data = json.loads(result.output)
    assert data['games'] == [{'appid': '42', 'name': 'Jogo A', 'needs_update': False},
                             {'appid': '43', 'name': 'Jogo B', 'needs_update': True}]
    assert data['libraries_checked'] == 2 and data['incomplete'] == 2


def test_steam_manifests_reject_traversal_duplicates_and_excessive_files(tmp_path, monkeypatch):
    _, library = steam_fixture(tmp_path, monkeypatch)
    write_manifest(library, '42', 'Escape', '../outside', create_directory=False)
    write_manifest(library, '43', 'Jogo correto', 'game')
    (library / 'steamapps' / 'appmanifest_44.acf').write_text('"AppState" { "appid" "44" "appid" "45" }')
    (library / 'steamapps' / 'appmanifest_45.acf').write_bytes(b' ' * 65_537)
    catalog = apps.steam_game_catalog()
    assert [game['appid'] for game in catalog['games']] == ['43']
    assert catalog['unreadable'] == 3


def test_steam_catalog_has_filter_and_pagination(tmp_path, monkeypatch):
    _, library = steam_fixture(tmp_path, monkeypatch)
    write_manifest(library, '42', 'Game A', 'a')
    write_manifest(library, '43', 'Game B', 'b')
    tool = UITool(tmp_path / 'shots')
    first = json.loads(tool.list_steam_games({'limit': 1}).output)
    assert first['games'][0]['appid'] == '42' and first['next_offset'] == 1
    second = json.loads(tool.list_steam_games({'limit': 1, 'offset': 1}).output)
    assert second['games'][0]['appid'] == '43' and second['next_offset'] is None
    filtered = json.loads(tool.list_steam_games({'query': 'game b'}).output)
    assert filtered['total'] == 1 and filtered['games'][0]['appid'] == '43'
    assert not tool.list_steam_games({'limit': True}).ok


@pytest.mark.parametrize('source', [
    '"root" { "key" "unterminated', '"root" { "key" "value"',
    '"root" { "Key" "one" "key" "two" }', '#include "other.vdf"',
    '"root" { "nested" ' * 10 + '"value"' + '}' * 10,
])
def test_keyvalues_rejects_ambiguous_or_unsupported_input(tmp_path, source):
    path = tmp_path / 'fixture.acf'
    path.write_text(source)
    with pytest.raises(ValueError):
        apps._read_keyvalues(path)
