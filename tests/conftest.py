"""Own one QApplication for the test session and dispose it before Python exits."""

import pytest
import os
import time
from pathlib import Path


def pytest_configure(config):
    # Keep runtime copies and generated fixtures on the project's volume. Let
    # pytest retain/clean its numbered runs normally; respect explicit overrides.
    if not config.option.basetemp and not os.environ.get("PYTEST_DEBUG_TEMPROOT"):
        directory = Path(__file__).resolve().parents[1] / "build" / "test-temp"
        directory.mkdir(parents=True, exist_ok=True)
        os.environ["PYTEST_DEBUG_TEMPROOT"] = str(directory)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    lifecycle = getattr(app, "_nyx_studio_lifecycle", None)
    if lifecycle is not None:
        assert not lifecycle.busy_windows(), "Studio workers survived their tests"
    windows = list(app.topLevelWidgets())
    for window in windows:
        window.close()
    pools = [pool for window in windows if not sip.isdeleted(window)
             for pool in window.findChildren(QThreadPool)]
    deadline = time.monotonic() + 10
    while any(pool.activeThreadCount() for pool in pools if not sip.isdeleted(pool)) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert not any(pool.activeThreadCount() for pool in pools if not sip.isdeleted(pool)), 'Qt workers survived shutdown'
    for window in windows:
        if not sip.isdeleted(window):
            window.deleteLater()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # Destroy native Qt objects while Python callbacks and module globals are
    # still valid, rather than relying on interpreter-finalization order.
    sip.delete(app)
