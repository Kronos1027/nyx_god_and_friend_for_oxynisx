"""Trusted owned Qt fixture: quit while a studio worker is still active."""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from tools.workspace_tool import WorkspaceTool  # noqa: E402
from ui.workspace_window import WorkspaceWindow  # noqa: E402


def main():
    app = QApplication([])
    window = WorkspaceWindow(project_directory=Path(sys.argv[1]) / "catalog")
    window.show()
    completed = threading.Event()
    ticks = []
    rejected = []

    def operation():
        # Only an owned fixture marker. No project code or external application.
        threading.Event().wait(0.3)
        completed.set()

    panel = window.packages_panel if len(sys.argv) > 2 and sys.argv[2] == "packages" else window.projects_panel
    panel.start(operation, lambda _: None)
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start()
    tool = WorkspaceTool()
    QTimer.singleShot(0, app.quit)
    QTimer.singleShot(50, lambda: rejected.append(not tool.run({"content": "late"}).ok))
    QTimer.singleShot(3000, app.exit)  # fixture guard; normal quit must occur first
    app.exec()
    assert completed.is_set()
    assert panel.job is None
    assert panel.cancelled.is_set()
    assert len(ticks) >= 2 and rejected == [True]
    print("shutdown waited; GUI responsive; late display rejected")


if __name__ == "__main__":
    main()
