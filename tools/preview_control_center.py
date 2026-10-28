"""Owned offline fixture for visual review; never opens personal databases."""

from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6 import sip  # noqa: E402
from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
import audio.tts  # noqa: E402
from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OfflineLLM  # noqa: E402
from core.scheduler import ReminderScheduler  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402
from ui.chat_store import ChatStore  # noqa: E402
from ui.desktop import DesktopWindow  # noqa: E402
from ui.overlay import OverlayWindow  # noqa: E402
from ui.workspace_window import WorkspaceWindow  # noqa: E402


class SilentVoice:
    enabled = False

    def speak(self, _):
        pass

    def stop_current(self):
        pass

    def shutdown(self):
        pass


def main():
    output = ROOT / "build/previews"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="desktop-preview-", dir=output) as temp:
        base = Path(temp)
        app = QApplication([])
        audio.tts.TextToSpeech = SilentVoice
        registry = ToolRegistry()
        registry.reminder_scheduler = ReminderScheduler(base / "reminders.db")
        loop = AgentLoop(OfflineLLM(), registry, AuditLogger(base / "logs", session_id="visual-fixture"))
        window = DesktopWindow(OverlayWindow(loop), ChatStore(base / "chats.db"),
                               QSettings(str(base / "settings.ini"), QSettings.Format.IniFormat))
        window.motion_check.setChecked(False)
        window.show()
        for name, width, height, theme in (("control-center-wide", 1440, 900, "midnight"),
                                            ("control-center-compact", 920, 680, "midnight"),
                                            ("control-center-daylight", 1280, 860, "daylight")):
            window.resize(width, height)
            window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
            for _ in range(5):
                app.processEvents()
                time.sleep(0.02)
            window._refresh_status()
            window.grab().save(str(output / (name + ".png")))
            print(name, window.size().width(), window.size().height())
        window.theme_combo.setCurrentIndex(window.theme_combo.findData("midnight"))
        window.resize(1280, 860)
        for name, page in (("chat", 0), ("agenda", 1), ("settings", 2), ("learning", 3)):
            window.set_page(page)
            app.processEvents()
            window.grab().save(str(output / (name + "-refreshed.png")))
        window.set_page(2)
        for index in range(window.settings_tabs.count()):
            window.settings_tabs.setCurrentIndex(index)
            app.processEvents()
            window.grab().save(str(output / f"settings-{index}.png"))
        studio = WorkspaceWindow(project_directory=base / "projects", package_directory=base / "packages")
        studio.resize(860, 680)
        studio.show()
        for index in range(studio.tabs.count()):
            studio.tabs.setCurrentIndex(index)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                app.processEvents()
                if not any(panel.job is not None for panel in studio.background_panels):
                    break
                time.sleep(0.01)
            app.processEvents()
            studio.grab().save(str(output / f"studio-{index}.png"))
        studio.close()
        window.resize(920, 680)
        window.font_slider.setValue(18)
        for page in (4, 2):
            window.set_page(page)
            app.processEvents()
            window.grab().save(str(output / f"large-text-{page}.png"))
        window.close()
        app.processEvents()
        sip.delete(app)


if __name__ == "__main__":
    main()
