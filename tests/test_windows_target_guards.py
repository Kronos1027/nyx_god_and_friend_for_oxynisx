"""Unit guards; these are not evidence of real Windows automation."""
import sys
from types import SimpleNamespace

import pytest

from tools.ui_tool import UITool
from tools.windows_targets import select_window


def test_duplicate_titles_need_explicit_handle(monkeypatch):
    windows = [SimpleNamespace(title="Same", _hWnd=i) for i in (1, 2)]
    monkeypatch.setitem(sys.modules, "pygetwindow", SimpleNamespace(getAllWindows=lambda: windows))
    with pytest.raises(ValueError, match="ambíguo"):
        select_window({"title": "Same"})
    assert select_window({"hwnd": 2}) is windows[1]


def test_no_active_window_never_chooses_first_window(monkeypatch):
    monkeypatch.setitem(sys.modules, "pygetwindow", SimpleNamespace(getActiveWindow=lambda: None))
    with pytest.raises(ValueError, match="não encontrada"):
        select_window({}, allow_active=True)


@pytest.mark.parametrize("target", ['notepad" & calc.exe', 'test.ps1', 'script.bat', 'script.py', '../evil.exe'])
def test_app_launch_rejects_shell_injection_and_scripts(tmp_path, monkeypatch, target):
    monkeypatch.setattr("os.startfile", lambda *a: pytest.fail("must not launch"), raising=False)
    assert not UITool(tmp_path).open_app({"app": target}).ok


def test_failsafe_is_failure_not_simulated_success(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("PyAutoGUI fail-safe triggered")
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(moveTo=fail, scroll=fail, press=fail))
    ui = UITool(tmp_path)
    for action, params in (("mouse_move", {"x": 2, "y": 2}), ("mouse_scroll", {"clicks": 1}),
                           ("set_volume", {}), ("mute_volume", {})):
        assert not ui.run({"action": action, **params}).ok


def test_destructive_aliases_keep_confirmation(tmp_path):
    ui = UITool(tmp_path)
    assert ui.is_destructive("terminate_process", {"pid": 123})
    assert ui.is_destructive("press_key", {"key": "shift+delete"})


def test_screenshot_cannot_escape_its_directory(tmp_path):
    ui = UITool(tmp_path)
    for filename in ("../elsewhere.png", "C:\\elsewhere.png", "file:stream.png"):
        assert not ui.take_screenshot({"filename": filename}).ok


def test_expired_snapshot_fails_before_any_window_access(monkeypatch):
    from core.operation_control import OperationControl
    from tools.windows_targets import UIATargets
    targets = UIATargets(OperationControl(), clock=lambda: 31)
    targets.snapshot, targets.created = "old", 0
    monkeypatch.setattr("tools.windows_targets.select_window", lambda p: pytest.fail("stale lookup"))
    with pytest.raises(ValueError, match="antiga"):
        targets.resolve({"snapshot": "old", "id": 1})


def test_pid_reuse_never_terminates_a_different_process(tmp_path, monkeypatch):
    process = SimpleNamespace(create_time=lambda: 9, terminate=lambda: pytest.fail("must not terminate"))
    monkeypatch.setattr("psutil.Process", lambda pid: process)
    result = UITool(tmp_path).kill_process({"pid": 999999, "created": 8})
    assert not result.ok and "reutilizado" in result.error
