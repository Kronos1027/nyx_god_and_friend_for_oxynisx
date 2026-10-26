import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from PyQt6.QtCore import QThread, QTimer

from core.operation_control import OperationControl, operation_scope
from tools.registry import ToolResult
from tools.workspace_tool import WorkspaceTool
from ui.workspace_window import WorkspaceWindow


@pytest.fixture
def ui(tmp_path, monkeypatch, qapp):
    app = qapp
    window = WorkspaceWindow(project_directory=tmp_path / "catalog")
    monkeypatch.setattr(WorkspaceWindow, "_instance", window)
    yield app, window
    deadline = time.monotonic() + 10
    while window.telemetry_job is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.telemetry_job is None
    app.processEvents()
    window.close()


def start_worker(operation):
    results = []
    thread = threading.Thread(target=lambda: results.append(operation()))
    thread.start()
    return thread, results


def finish_worker(app, thread):
    deadline = time.monotonic() + 5
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        thread.join(0.005)
    assert not thread.is_alive()


def test_real_worker_displays_on_gui_thread_only_after_acknowledgement(ui, monkeypatch):
    app, window = ui
    tool = WorkspaceTool()
    threads = []
    original = window.display_code

    def display(*args, **kwargs):
        threads.append(QThread.currentThread())
        return original(*args, **kwargs)

    monkeypatch.setattr(window, "display_code", display)
    thread, results = start_worker(lambda: tool.run({"content": "print(96)"}))
    finish_worker(app, thread)
    assert results[0].ok and results[0].meta["displayed"]
    assert threads == [app.thread()]
    assert window.txt_code.toPlainText() == "print(96)"
    assert window.isVisible()


def test_timeout_discards_queued_display_and_bounds_queue(ui):
    app, window = ui
    tool = WorkspaceTool(timeout=0.05)
    thread, results = start_worker(lambda: tool.run({"content": "expired"}))
    thread.join(1)  # deliberately do not pump GUI events yet
    assert not thread.is_alive()
    assert not results[0].ok and not results[0].meta["outcome_unknown"]
    assert not tool.run({"content": "cannot accumulate queue"}).ok
    app.processEvents()
    assert window.txt_code.toPlainText() == ""
    assert not window.isVisible()
    assert tool.run({"content": "fresh"}).ok


def test_local_cancellation_survives_global_reset_before_delivery(ui):
    app, window = ui
    control, cancelled = OperationControl(), threading.Event()
    tool = WorkspaceTool(control=control)

    def operation():
        with operation_scope(cancelled.is_set):
            return tool.run({"content": "must not appear"})

    thread, results = start_worker(operation)
    deadline = time.monotonic() + 1
    while tool.dispatcher.pending is None and time.monotonic() < deadline:
        time.sleep(0.001)
    assert tool.dispatcher.pending is not None
    cancelled.set()
    control.resume()
    thread.join(1)
    assert not thread.is_alive() and not results[0].ok
    app.processEvents()
    assert not window.isVisible()


def test_render_failure_is_not_reported_as_success(ui, monkeypatch):
    app, window = ui
    tool = WorkspaceTool()

    def fail(*args, **kwargs):
        raise RuntimeError("fixture render failure")

    monkeypatch.setattr(window, "display_document", fail)
    thread, results = start_worker(lambda: tool.run({"view": "doc", "content": "report"}))
    finish_worker(app, thread)
    assert not results[0].ok
    assert "fixture render failure" in results[0].error
    assert results[0].meta["outcome_unknown"]
    assert tool.last_display == {}


def test_timeout_after_render_started_reports_unknown_outcome(ui, monkeypatch):
    app, window = ui
    tool = WorkspaceTool(timeout=0.05)
    returned = threading.Event()
    original = window.display_code

    def slow_render(*args, **kwargs):
        assert returned.wait(2)
        original(*args, **kwargs)

    monkeypatch.setattr(window, "display_code", slow_render)

    def run():
        result = tool.run({"content": "already started"})
        returned.set()
        return result

    thread, results = start_worker(run)
    finish_worker(app, thread)
    assert not results[0].ok and results[0].meta["outcome_unknown"]
    assert window.isVisible()
    assert tool.last_display == {}


def test_headless_process_returns_failure_without_creating_application():
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    completed = subprocess.run(
        [sys.executable, "-c", "from tools.workspace_tool import WorkspaceTool; "
         "from PyQt6.QtWidgets import QApplication; "
         "r=WorkspaceTool().run({'content':'fixture'}); "
         "assert not r.ok and QApplication.instance() is None; print('headless rejected')"],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert "headless rejected" in completed.stdout


@pytest.mark.parametrize("kind", ["projects", "packages"])
def test_application_quit_waits_for_studio_worker_in_real_process(tmp_path, kind):
    completed = subprocess.run(
        [sys.executable, "tools/studio_shutdown_fixture.py", str(tmp_path), kind],
        capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "shutdown waited; GUI responsive; late display rejected" in completed.stdout


def test_telemetry_io_does_not_block_gui_and_close_preserves_worker(ui, monkeypatch):
    from tools.project_watch_tool import ProjectWatchTool

    app, window = ui
    entered, release = threading.Event(), threading.Event()
    ticks = []

    def slow(*_):
        entered.set()
        assert release.wait(3)
        return ToolResult(True, output="Measured fixture")

    monkeypatch.setattr(ProjectWatchTool, "run", slow)
    try:
        result = WorkspaceTool().run({"view": "telemetry"})
        assert result.ok and result.meta["telemetry_pending"]
        assert entered.wait(1)
        QTimer.singleShot(0, lambda: ticks.append(True))
        app.processEvents()
        assert ticks == [True]
        window.close()
        assert window.isVisible()
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while window.telemetry_job is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert window.telemetry_job is None
    assert window.lbl_hw_info.text() == "Measured fixture"


@pytest.mark.parametrize("params", [
    {"view": None}, {"title": ["invalid"]}, {"content": "x" * 256001},
    {"view": "sheet", "content": []}, {"view": "sheet", "content": [["x"]] * 1001},
    {"view": "sheet", "content": [["x"] * 51]},
    {"view": "sheet", "content": [["x"], {"a": 1}]},
    {"view": "sheet", "content": [[{}]]},
])
def test_invalid_payload_is_rejected_before_gui(ui, params):
    _, window = ui
    assert not WorkspaceTool().run(params).ok
    assert not window.isVisible()


def test_quoted_csv_and_wider_second_row_preserve_cells(ui):
    _, window = ui
    result = WorkspaceTool().run({"view": "sheet", "content": '"a,b",c\nx,y,z'})
    assert result.ok
    assert window.table.item(0, 0).text() == "a,b"
    assert window.table.item(1, 2).text() == "z"
