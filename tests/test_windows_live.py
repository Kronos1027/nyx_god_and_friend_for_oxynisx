"""Opt-in native UIA acceptance, only against an owned Qt fixture process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest

from tools.ui_tool import UITool

pytestmark = pytest.mark.skipif(os.name != "nt" or os.environ.get("NYX_TEST_DESKTOP") != "1",
                               reason="owned Windows fixture opt-in")


class RuntimeWorker:
    """Run real tools off the Qt thread while the existing UI pumps its events."""
    def __init__(self, tool):
        self.tool = tool

    def __getattr__(self, name):
        member = getattr(self.tool, name)
        if not callable(member):
            return member
        def call(*args, **kwargs):
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None or QThread.currentThread() != app.thread():
                return member(*args, **kwargs)
            results, errors = [], []
            def work():
                try:
                    results.append(member(*args, **kwargs))
                except Exception as exc:
                    errors.append(exc)
            thread = threading.Thread(target=work)
            thread.start()
            deadline = time.monotonic() + 8
            while thread.is_alive() and time.monotonic() < deadline:
                app.processEvents()
                thread.join(0.005)
            assert not thread.is_alive(), "Real UIA worker exceeded fixture deadline"
            if errors:
                raise errors[0]
            return results[0]
        return call


@pytest.fixture(scope="module", params=("1.0", "1.5"))
def desktop_fixture(tmp_path_factory, request):
    directory = tmp_path_factory.mktemp("windows-owned-fixture")
    state_path = directory / "state.json"
    title = "Nyx UI Fixture " + uuid4().hex[:8]
    root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    env["QT_SCALE_FACTOR"] = request.param
    process = subprocess.Popen([sys.executable, str(root / "tools/windows_test_app.py"),
        "--title", title, "--state", str(state_path)], env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 10
        while not state_path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert state_path.exists(), "Owned fixture did not start"
        hwnd = json.loads(state_path.read_text(encoding="utf-8"))["hwnd"]
        ui = UITool(directory / "screenshots")
        yield RuntimeWorker(ui), {"hwnd": hwnd, "title": title}, state_path
    finally:
        if 'ui' in locals():
            ui.targets.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def inspect(ui, target):
    result = ui.inspect_elements(target)
    assert result.ok, result.error
    assert result.meta["hwnd"] == target["hwnd"]
    return result.meta


def params_for(info, name):
    item = next(e for e in info["elements"] if e["name"] == name)
    return {"snapshot": info["snapshot"], "id": item["id"]}


def test_native_uia_edit_click_read_and_independent_state(desktop_fixture):
    ui, target, path = desktop_fixture
    info = inspect(ui, target)
    edit = params_for(info, "Fixture input")
    filled = ui.run({"action": "type_element", **edit, "text": "Nyx ação 🌙"})
    assert filled.ok and filled.meta["verified"], filled.error
    assert ui.run({"action": "read_element", **edit}).meta["text"] == "Nyx ação 🌙"
    result_label = params_for(info, "Waiting")
    clicked = ui.click_element(params_for(info, "Apply fixture"))
    assert clicked.ok and not clicked.meta["verified"], clicked.error
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state["clicks"]:
            break
        time.sleep(0.05)
    assert state["text"] == "Nyx ação 🌙" and state["clicks"] == 1
    assert ui.run({"action": "read_element", **result_label}).meta["text"] == "Result: Nyx ação 🌙"


def test_stale_password_disabled_and_ambiguous_targets_are_rejected(desktop_fixture):
    ui, target, _ = desktop_fixture
    old = inspect(ui, target)
    current = inspect(ui, target)
    assert not ui.click_element(params_for(old, "Apply fixture")).ok
    assert not ui.click_element(params_for(current, "Disabled fixture")).ok
    assert not ui.click_element({"snapshot": current["snapshot"], "name": "Duplicate fixture"}).ok
    secret = next(e for e in current["elements"] if e["password"])
    assert not ui.run({"action": "read_element", "snapshot": current["snapshot"], "id": secret["id"]}).ok


def test_snapshot_crosses_worker_threads_without_com_pointer_reuse(desktop_fixture):
    ui, target, _ = desktop_fixture
    data = []
    def collect():
        data.append(ui.inspect_elements(target))
    thread = threading.Thread(target=collect)
    thread.start()
    thread.join(5)
    assert not thread.is_alive() and data and data[0].ok
    info = data[0].meta
    result = ui.run({"action": "read_element", **params_for(info, "Fixture input")})
    assert result.ok, result.error


def test_capture_is_physical_and_limited_to_owned_window(desktop_fixture):
    from PIL import Image
    ui, target, _ = desktop_fixture
    assert ui.focus_window(target).ok
    shot = ui.take_screenshot(target)
    assert shot.ok, shot.error
    assert shot.meta["hwnd"] == target["hwnd"]
    assert shot.meta["coordinate_space"] == "physical_pixels"
    with Image.open(shot.meta["path"]) as image:
        assert image.size == (shot.meta["width"], shot.meta["height"])
    assert 400 <= shot.meta["width"] <= 1000


def test_modal_requires_correct_window_and_rejects_parent_input(desktop_fixture):
    ui, target, path = desktop_fixture
    info = inspect(ui, target)
    opened = ui.click_element(params_for(info, "Open modal fixture"))
    assert opened.ok, opened.error
    import win32gui
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("modal_hwnd") and win32gui.IsWindowVisible(state["modal_hwnd"]):
            break
        time.sleep(0.03)
    try:
        assert not ui.click_element(params_for(info, "Apply fixture")).ok
        assert not ui.focus_window({"title": target["title"]}).ok
        modal = inspect(ui, {"hwnd": state["modal_hwnd"]})
        assert ui.click_element(params_for(modal, "Dismiss fixture")).ok
    finally:
        if state.get("modal_hwnd") and win32gui.IsWindow(state["modal_hwnd"]):
            # Close only the owned fixture dialog, even after an assertion fails.
            win32gui.PostMessage(state["modal_hwnd"], 0x0010, 0, 0)
        ui.control.resume()


def test_physical_click_hits_only_chosen_owned_window(desktop_fixture):
    ui, target, path = desktop_fixture
    info = inspect(ui, target)
    button = next(e for e in info["elements"] if e["name"] == "Apply fixture")
    left, top, right, bottom = button["rect"]
    before = json.loads(path.read_text(encoding="utf-8"))["clicks"]
    result = ui.click_coordinate({**target, "x": (left+right)//2, "y": (top+bottom)//2})
    assert result.ok, result.error
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        after = json.loads(path.read_text(encoding="utf-8"))["clicks"]
        if after > before:
            break
        time.sleep(0.03)
    assert after == before + 1
    assert not ui.click_coordinate({**target, "x": -10000, "y": -10000}).ok
