import os
import time
import zipfile

import pytest
from PyQt6.QtWidgets import QFileDialog

from ui.workspace_window import WorkspaceWindow

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows package snapshots")


def wait(app, panel):
    deadline = time.monotonic() + 10
    while panel.job is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert panel.job is None


@pytest.fixture
def panel(tmp_path, qapp):
    app = qapp
    window = WorkspaceWindow(project_directory=tmp_path / "projects", package_directory=tmp_path / "packages")
    yield app, window, window.packages_panel
    wait(app, window.packages_panel)
    window.close()


def source(tmp_path, text="First version"):
    folder = tmp_path / "example-skill"
    folder.mkdir(exist_ok=True)
    (folder / "SKILL.md").write_text("---\nname: example-skill\ndescription: Pacote de exemplo\n---\n" + text,
                                    encoding="utf-8")
    return folder


def test_ui_import_versions_search_and_export(panel, tmp_path, monkeypatch):
    app, window, pane = panel
    folder = source(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: str(folder))
    pane.import_folder()
    wait(app, pane)
    assert pane.packages.currentData() == "example-skill"
    assert "inativa" in pane.status.text()
    assert "não executados" in pane.status.text()
    assert "First version" in pane.preview.toPlainText()
    assert str(folder) in pane.details.text()
    source(tmp_path, "Second version")
    pane.import_folder()
    wait(app, pane)
    assert pane.versions.count() == 2 and pane.versions.currentData()["version"] == 2
    pane.versions.setCurrentIndex(1)
    wait(app, pane)
    assert "First version" in pane.preview.toPlainText()
    destination = tmp_path / "export.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_: (str(destination), "ZIP"))
    pane.export()
    wait(app, pane)
    with zipfile.ZipFile(destination) as archive:
        assert b"First version" in archive.read("example-skill/SKILL.md")
    pane.query.setText("absent")
    pane.refresh()
    wait(app, pane)
    assert pane.packages.count() == 0 and not pane.export_button.isEnabled()
    assert pane.preview.toPlainText() == ""
    pane.query.setText("exemplo")
    pane.refresh()
    wait(app, pane)
    assert pane.packages.count() == 1
    assert window.tabs.tabText(5) == "Habilidades"


def test_corrupt_package_clears_preview_and_blocks_export(panel, tmp_path, monkeypatch):
    app, _, pane = panel
    folder = source(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: str(folder))
    pane.import_folder()
    wait(app, pane)
    with pane.store().artifacts._db() as db:
        db.execute("UPDATE files SET content=?", (b"invalid",))
    pane.select_version()
    wait(app, pane)
    assert pane.status.text().startswith("Falha:")
    assert pane.package is None and not pane.export_button.isEnabled()
    assert pane.preview.toPlainText() == ""


def test_package_worker_does_not_block_ui_or_allow_early_close(panel):
    import threading
    from PyQt6.QtCore import QTimer

    app, window, pane = panel
    entered, release = threading.Event(), threading.Event()
    ticks = []

    def operation():
        entered.set()
        assert release.wait(3)

    window.show()
    pane.start(operation, lambda _: None)
    try:
        assert entered.wait(1)
        QTimer.singleShot(0, lambda: ticks.append(True))
        app.processEvents()
        assert ticks == [True]
        window.close()
        assert pane.cancelled.is_set() and window.isVisible()
    finally:
        release.set()
        wait(app, pane)
