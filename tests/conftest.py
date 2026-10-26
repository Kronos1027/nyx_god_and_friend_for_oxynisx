"""Own one QApplication for the test session and dispose it before Python exits."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    lifecycle = getattr(app, "_nyx_studio_lifecycle", None)
    if lifecycle is not None:
        assert not lifecycle.busy_windows(), "Studio workers survived their tests"
    for window in app.topLevelWidgets():
        window.close()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # Destroy native Qt objects while Python callbacks and module globals are
    # still valid, rather than relying on interpreter-finalization order.
    sip.delete(app)
