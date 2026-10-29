from pathlib import Path

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
