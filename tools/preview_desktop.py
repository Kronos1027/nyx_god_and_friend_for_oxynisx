"""Render the native desktop in isolated demo state for visual review."""

from __future__ import annotations

import os
import sys
import tempfile
import argparse
import json
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtCore import QSettings, QTimer, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtGui import QFont, QFontDatabase  # noqa: E402
from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OfflineLLM, create_llm_client  # noqa: E402
from core.scheduler import ReminderScheduler  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402
import audio.tts  # noqa: E402


class SilentVoice:
    enabled = False

    def speak(self, text):
        pass

    def stop_current(self):
        pass

    def shutdown(self):
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Exercise the real local model through the desktop")
    parser.add_argument("--research-live", action="store_true", help="Exercise idle research through the native UI with real HTTPS")
    args = parser.parse_args()
    audio.tts.TextToSpeech = SilentVoice
    from ui.desktop import DesktopWindow
    from ui.overlay import OverlayWindow

    app = QApplication.instance() or QApplication([])
    # The offscreen Windows plugin does not enumerate system fonts itself.
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "seguisym.ttf"):
        if (fonts / name).is_file():
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Segoe UI", 10))
    destination = ROOT / "build" / "previews"
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nyx-desktop-preview-") as directory:
        temporary = Path(directory)
        registry = ToolRegistry()
        registry.reminder_scheduler = ReminderScheduler(temporary / "schedule.db")
        from core.evolution import EvolutionLab
        from core.research import ResearchQueue
        registry.evolution_lab = EvolutionLab(temporary / "evolution.db")
        registry.research_queue = ResearchQueue(registry.evolution_lab)
        registry.research_queue.seed_curiosity()
        if args.live:
            from core.ollama_service import ensure_local_ollama

            service = ensure_local_ollama()
            print(service.reason, flush=True)
        client, backend = create_llm_client() if args.live else (OfflineLLM(), "demo")
        if args.live and isinstance(client, OfflineLLM):
            raise RuntimeError("No local model fits the current memory budget for a live check.")
        if args.live:
            client.keep_alive = "0"
        loop = AgentLoop(client, registry, AuditLogger(temporary / "logs", session_id="preview"))
        controller = OverlayWindow(loop)
        from ui.chat_store import ChatStore

        window = DesktopWindow(
            controller, ChatStore(temporary / "chats.db"),
            QSettings(str(temporary / "ui.ini"), QSettings.Format.IniFormat),
        )
        window.motion_check.setChecked(False)
        window.research_timer.stop()  # Screenshots never initiate background network work.
        window.resize(1440, 920)
        window.show()
        for theme in ("midnight", "daylight", "aurora"):
            window.theme_combo.setCurrentIndex(window.theme_combo.findData(theme))
            app.processEvents()
            window._refresh_status()
            app.processEvents()
            output = destination / f"desktop-{theme}{'-live' if args.live else ''}.png"
            if not window.grab().save(str(output)):
                raise RuntimeError(f"Não foi possível salvar {output}")
            print(output)
        if args.live:
            # No tools are registered; any accidental action request is denied
            # by this diagnostic rather than opening a modal dialog unattended.
            from ui.permission_dialog import PermissionDialog

            denied_requests = []

            def deny_diagnostic_action(*args, **kwargs):
                denied_requests.append(True)
                return False

            PermissionDialog.ask_confirmation = staticmethod(deny_diagnostic_action)
            results = []
            controller.action_observed.connect(results.append)
            responsive_ticks = []
            heartbeat = QTimer(window)
            heartbeat.setInterval(20)
            heartbeat.timeout.connect(lambda: responsive_ticks.append(time.monotonic()))
            heartbeat.start()
            window.set_page(0)
            window.theme_combo.setCurrentIndex(window.theme_combo.findData("midnight"))
            window.composer.setPlainText("Diga olá em português, em uma frase. Só converse, sem ferramentas.")
            started = time.monotonic()
            window.send_prompt()
            deadline = started + 120
            while window._busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            heartbeat.stop()
            app.processEvents()
            window._refresh_status()
            report = {
                "backend": backend,
                "duration_seconds": round(time.monotonic() - started, 2),
                "ui_event_ticks": len(responsive_ticks),
                "completed": not window._busy,
                "schema_valid": bool(results and results[0].response.parse_ok),
                "confirmation_requests": len(denied_requests),
                "action_types": [r.response.action.type for r in results],
                "tools_executed": any(r.executed for r in results),
                "messages": [{"role": m["role"], "content": m["content"]} for m in window.store.messages(window.chat_id)],
            }
            (destination / "live-ui-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            output = destination / "desktop-live-chat.png"
            window.grab().save(str(output))
            print(json.dumps(report, ensure_ascii=False))
            print(output)
            if not report["completed"] or not report["schema_valid"] or report["ui_event_ticks"] < 2 or report["confirmation_requests"] or report["tools_executed"]:
                raise RuntimeError("Live desktop smoke check did not pass; inspect live-ui-smoke.json.")
        if args.research_live:
            window.set_page(3)
            ticks = []
            heartbeat = QTimer(window)
            heartbeat.setInterval(20)
            heartbeat.timeout.connect(lambda: ticks.append(time.monotonic()))
            heartbeat.start()
            window._last_interaction = time.monotonic() - 61
            started = time.monotonic()
            window._research_tick()
            deadline = started + 30
            while window._research_busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            heartbeat.stop()
            jobs = registry.research_queue.list_jobs()
            report = {"completed": any(job["state"] == "completed" for job in jobs),
                      "seconds": round(time.monotonic() - started, 2), "ui_ticks": len(ticks),
                      "jobs": jobs, "knowledge_count": registry.evolution_lab.overview()["knowledge_count"]}
            (destination / "research-ui-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
            if not report["completed"] or report["ui_ticks"] < 2:
                raise RuntimeError("Idle UI research did not finish; inspect resource pressure and report")
        window.set_page(3)
        for index in range(window.study_jobs.count()):
            item = window.study_jobs.item(index)
            if item.data(Qt.ItemDataRole.UserRole)["state"] == "completed":
                window._show_study(item)
                break
        app.processEvents()
        output = destination / "desktop-learning.png"
        window.grab().save(str(output))
        print(output)
        window.set_page(2)
        app.processEvents()
        output = destination / "desktop-settings.png"
        window.grab().save(str(output))
        print(output)
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
