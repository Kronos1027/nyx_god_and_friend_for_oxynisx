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
    parser.add_argument("--task-demo", action="store_true", help="Render a scripted multi-step task with real temporary file reads")
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
        if args.task_demo:
            if args.live:
                raise ValueError("Use --task-demo separado de --live")
            from core.task_runner import TaskRunner
            from tools.registry import ToolSpec, ToolResult
            first, second = temporary / "a.txt", temporary / "b.txt"
            first.write_text("Quantidade A: 12", encoding="utf-8")
            second.write_text("Quantidade B: 7", encoding="utf-8")

            def read_fixture(params):
                path = Path(params.get("path", "")).resolve()
                if path not in {first.resolve(), second.resolve()}:
                    return ToolResult(False, error="Fora do diagnóstico")
                return ToolResult(True, path.read_text(encoding="utf-8"))

            registry.register(ToolSpec("read_file", "Diagnóstico"), read_fixture)
            for path in (first, second, None):
                client.queue(json.dumps({"reasoning": "Demonstração roteirizada", "alternative_suggestion": None,
                                         "emotion": "talk", "action": {"type": "read_file" if path else "none", "params": {"path": str(path)} if path else {}},
                                         "requires_confirmation": False, "confirmation_prompt": None,
                                         "speech_output": "Li os dois arquivos: A = 12 e B = 7. A soma é 19. Este é um teste com planejamento roteirizado."}))
            loop.task_runner = TaskRunner(loop)
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
        if args.task_demo:
            window.theme_combo.setCurrentIndex(window.theme_combo.findData("midnight"))
            window.composer.setPlainText("Demonstração: leia os dois arquivos de teste e some as quantidades.")
            window.send_prompt()
            deadline = time.monotonic() + 5
            while window._busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            app.processEvents()
            if window._busy or len(loop.task_runner.steps) != 2:
                raise RuntimeError("Demonstração de tarefa não terminou")
            output = destination / "desktop-task-demo.png"
            window.grab().save(str(output))
            print(output)
        # Inspect the connected social/privacy panels with temporary local state.
        window._interests.remember("Astronomia", kind="confirmed_preference", origin="Demonstração de interface")
        window._refresh_social()
        window.set_page(3)
        for index, label in ((3, "privacy"), (4, "interests")):
            window.learning_tabs.setCurrentIndex(index)
            app.processEvents()
            window.grab().save(str(destination / f"desktop-{label}.png"))
        window.set_page(0)
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
        from PyQt6.QtWidgets import QScrollArea
        ancestor = window.browser_persist_check.parentWidget()
        while ancestor and not isinstance(ancestor, QScrollArea):
            ancestor = ancestor.parentWidget()
        if ancestor:
            ancestor.ensureWidgetVisible(window.browser_preferences_note)
            app.processEvents()
            window.grab().save(str(destination / "desktop-browser-settings.png"))
        window.settings_tabs.setCurrentIndex(1)
        app.processEvents()
        window.grab().save(str(destination / "desktop-model-settings.png"))
        window.set_page(1)
        app.processEvents()
        window.grab().save(str(destination / "desktop-agenda.png"))
        window.set_page(3)
        for index, label in enumerate(("studies", "knowledge", "backups")):
            window.learning_tabs.setCurrentIndex(index)
            app.processEvents()
            window.grab().save(str(destination / f"desktop-{label}.png"))
        window.set_page(0)
        window.focus_button.setChecked(True)
        window.resize(920, 640)
        app.processEvents()
        window.grab().save(str(destination / "desktop-focus.png"))
        controller.show()
        app.processEvents()
        controller.grab().save(str(destination / "pet-compact.png"))
        controller._toggle_pet_controls()
        controller.say("Estou aqui. Podemos conversar ou trabalhar em uma ideia.")
        app.processEvents()
        controller.grab().save(str(destination / "pet-conversation.png"))
        from ui.workspace_window import WorkspaceWindow
        studio = WorkspaceWindow()
        studio.setStyleSheet(window.styleSheet())
        studio.show()
        app.processEvents()
        studio.grab().save(str(destination / "desktop-studio.png"))
        studio.close()
        from ui.permission_dialog import PermissionDialog
        permission = PermissionDialog({"type": "file", "params": {"operation": "write", "path": "exemplo.txt"}}, parent=window)
        permission.show()
        app.processEvents()
        permission.grab().save(str(destination / "desktop-permission.png"))
        permission.reject()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
