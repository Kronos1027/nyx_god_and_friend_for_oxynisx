import os
import time
import zipfile

import pytest
from PyQt6.QtWidgets import QApplication, QFileDialog

from ui.workspace_window import WorkspaceWindow

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows file snapshot UI")


@pytest.fixture
def studio(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = WorkspaceWindow(project_directory=tmp_path / "catalog")
    yield app, window
    await_job(app, window.projects_panel)
    window.close()


def await_job(app, pane):
    deadline = time.monotonic() + 10
    while pane.job is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert pane.job is None, "Project worker did not finish"


def test_studio_save_code_restore_preview_and_export(studio, tmp_path, monkeypatch):
    app, window = studio
    pane = window.projects_panel
    window.display_code("print(96)", title="Soma")
    window._save_code_project()
    await_job(app, pane)
    assert pane.projects.currentText() == "Soma"
    assert pane.versions.currentData() == 1
    assert pane.files.item(0).text() == "main.py"
    assert pane.preview.toPlainText() == "print(96)"
    assert "Testes não executados" in pane.status.text()
    pane.restore()
    await_job(app, pane)
    assert pane.versions.currentData() == 2
    assert pane.versions.count() == 2
    target = tmp_path / "export.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(target), "ZIP"))
    pane.export()
    await_job(app, pane)
    with zipfile.ZipFile(target) as archive:
        assert archive.read("main.py") == b"print(96)"
    pane.refresh()
    await_job(app, pane)
    assert pane.versions.count() == 2


def test_import_folder_and_failure_keep_original_version(studio, tmp_path, monkeypatch):
    app, window = studio
    pane = window.projects_panel
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("print('A')")
    (source / ".env").write_text("synthetic secret")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: str(source))
    pane.import_folder()
    await_job(app, pane)
    assert pane.files.count() == 1
    assert "1 entradas excluídas" in pane.status.text()
    (source / "a.py").write_text("print('B')")
    pane.save_folder()
    await_job(app, pane)
    assert pane.versions.currentData() == 2
    assert pane.preview.toPlainText() == "print('B')"
    target = tmp_path / "existing.zip"
    target.write_bytes(b"preserve")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(target), "ZIP"))
    pane.export()
    await_job(app, pane)
    assert pane.status.text().startswith("Falha:")
    assert target.read_bytes() == b"preserve"


def test_legacy_script_button_cannot_execute_host_code(studio, tmp_path):
    _, window = studio
    sentinel = tmp_path / "must-not-exist"
    window.display_code(f"from pathlib import Path; Path({str(sentinel)!r}).write_text('unsafe')")
    assert not window.btn_run.isEnabled()
    window._run_code()  # even a direct call must not bypass the UI restriction
    assert not sentinel.exists()
    assert "bloqueada" in window.lbl_status.text()


def test_failed_version_load_cannot_export_previous_version(studio):
    app, window = studio
    pane = window.projects_panel
    pane.save_code("History", "print(1)")
    await_job(app, pane)
    pane.restore()
    await_job(app, pane)
    store = pane.store()
    with store._db() as db:
        db.execute("UPDATE files SET content=? WHERE version=1", (b"corrupted",))
    pane.versions.setCurrentIndex(pane.versions.findData(1))
    await_job(app, pane)
    assert pane.status.text().startswith("Falha:")
    assert pane.snapshot is None
    assert pane.preview.toPlainText() == ""
    assert not pane.buttons[3].isEnabled()


def test_project_worker_keeps_gui_alive_and_close_waits(studio):
    import threading
    from PyQt6.QtCore import QTimer

    app, window = studio
    pane = window.projects_panel
    entered, release = threading.Event(), threading.Event()
    ticks = []

    def blocked_io():
        entered.set()
        assert release.wait(3)

    window.show()
    pane.start(blocked_io, lambda _: pane.status.setText("Finished"))
    try:
        assert entered.wait(1)
        QTimer.singleShot(0, lambda: ticks.append(True))
        app.processEvents()
        assert ticks == [True]
        window.close()
        assert window.isVisible()
        assert pane.cancelled.is_set()
        assert pane.job is not None
    finally:
        release.set()
        await_job(app, pane)
    window.close()
    assert not window.isVisible()
