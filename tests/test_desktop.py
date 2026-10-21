import json
import time

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.scheduler import ReminderScheduler
from tools.registry import ToolRegistry
from ui.chat_store import ChatStore
from ui.desktop import DesktopWindow
from ui.overlay import OverlayWindow


class SilentVoice:
    enabled = False

    def __init__(self):
        self.shutdown_calls = 0

    def speak(self, text):
        pass

    def stop_current(self):
        pass

    def shutdown(self):
        self.shutdown_calls += 1


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("audio.tts.TextToSpeech", SilentVoice)
    registry = ToolRegistry()
    registry.reminder_scheduler = ReminderScheduler(tmp_path / "reminders.db")
    llm = OfflineLLM()
    loop = AgentLoop(llm, registry, AuditLogger(tmp_path / "logs", session_id="ui-test"))
    controller = OverlayWindow(loop)
    settings = QSettings(str(tmp_path / "desktop.ini"), QSettings.Format.IniFormat)
    window = DesktopWindow(controller, ChatStore(tmp_path / "chats.db"), settings)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    app.processEvents()
    yield window, app, llm
    window.close()
    app.processEvents()


def _wait(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_research_controls_persist_cancel_and_display_collected_text(desktop, tmp_path):
    from core.evolution import EvolutionLab
    from core.research import ResearchQueue

    window, app, _ = desktop
    lab = EvolutionLab(tmp_path / "research.db")
    queue = ResearchQueue(lab)
    window.controller.loop.registry.evolution_lab = lab
    window.controller.loop.registry.research_queue = queue
    window.set_page(3)
    window.study_topic.setText("Meu estudo")
    window._enqueue_study()
    assert len(queue.list_jobs()) == 1
    assert window.study_jobs.count() == 1
    queue.run_one(lambda url: (url, "Texto externo <script>não executar</script>"))
    window._refresh_learning()
    window._show_study(window.study_jobs.item(0))
    assert "<script>não executar</script>" in window.study_preview.toPlainText()
    window.study_topic.setText("Novo estudo")
    window.study_source.setCurrentIndex(1)
    window._enqueue_study()
    window.study_jobs.setCurrentRow(0)
    window._cancel_study()
    assert queue.list_jobs()[0]["state"] == "cancelled"
    window.research_check.setChecked(False)
    assert window.settings.value("idle_research", type=bool) is False
    assert window._research_cancel.is_set()


def test_desktop_task_resumes_multiple_confirmations_and_records_progress(desktop, monkeypatch):
    from core.task_runner import TaskRunner
    from tools.registry import ToolSpec, ToolResult
    from ui.permission_dialog import PermissionDialog

    window, app, llm = desktop
    loop = window.controller.loop
    loop.task_runner = TaskRunner(loop)
    executed = []
    loop.registry.register(ToolSpec("shell", "test", destructive=True), lambda p: (executed.append(p) or ToolResult(True, "ok")))
    for number in (1, 2, 0):
        llm.queue(json.dumps({"reasoning": "test", "alternative_suggestion": None, "emotion": "talk",
                             "action": {"type": "shell" if number else "none", "params": {"n": number} if number else {}},
                             "requires_confirmation": False, "confirmation_prompt": None, "speech_output": "Final"}))
    approvals = []
    monkeypatch.setattr(PermissionDialog, "ask_confirmation", staticmethod(lambda pending, **kwargs: (approvals.append(pending) or True)))
    window.composer.setPlainText("Duas etapas")
    window.send_prompt()
    _wait(app, lambda: not window._busy)
    assert executed == [{"n": 1}, {"n": 2}]
    assert len(approvals) == 2
    assert len(loop.history) == 2
    assert not window.cancel_task_button.isEnabled()
    assert any("Etapa 2" in window.activity.item(i).text() for i in range(window.activity.count()))


def test_desktop_cancel_during_generation_prevents_action(desktop):
    import threading
    from core.task_runner import TaskRunner
    from tools.registry import ToolSpec, ToolResult

    window, app, llm = desktop
    loop = window.controller.loop
    loop.task_runner = TaskRunner(loop)
    started, release = threading.Event(), threading.Event()
    calls = []
    loop.registry.register(ToolSpec("read_file", "read"), lambda p: (calls.append(p) or ToolResult(True, "data")))

    def generate(*args, **kwargs):
        started.set()
        release.wait(2)
        return json.dumps({"reasoning": "test", "alternative_suggestion": None, "emotion": "talk",
                           "action": {"type": "read_file", "params": {}}, "requires_confirmation": False,
                           "confirmation_prompt": None, "speech_output": "read"})

    llm.generate = generate
    window.composer.setPlainText("Leia")
    window.send_prompt()
    try:
        _wait(app, started.is_set)
        assert window.cancel_task_button.isEnabled()
        window.cancel_task_button.click()
    finally:
        release.set()
    _wait(app, lambda: not window._busy)
    assert calls == []
    assert "interrompido" in window.store.messages(window.chat_id)[-1]["content"]


def test_desktop_submission_runs_real_controller_and_restores_chat_context(desktop):
    window, app, llm = desktop
    llm.queue(json.dumps({
        "reasoning": "Resposta de teste",
        "alternative_suggestion": None,
        "emotion": "talk",
        "action": {"type": "none", "params": {}},
        "requires_confirmation": False,
        "confirmation_prompt": None,
        "speech_output": "Olá! Vamos trabalhar juntos.",
    }))
    first_chat = window.chat_id
    window.composer.setPlainText("Olá, Nyx")
    window.send_prompt()
    _wait(app, lambda: not window._busy)

    messages = window.store.messages(first_chat)
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Olá, Nyx"), ("assistant", "Olá! Vamos trabalhar juntos."),
    ]
    assert llm.received == ["Olá, Nyx"]
    assert window.send_button.isEnabled()
    window.new_chat()
    assert window.chat_id != first_chat
    assert window.controller.loop.history == []
    window.activate_chat(first_chat)
    assert window.controller.loop.history[-1]["content"] == "Olá! Vamos trabalhar juntos."


def test_desktop_agenda_controls_write_and_cancel_persistent_reminders(desktop):
    window, app, _ = desktop
    window.set_page(1)
    window.reminder_text.setText("Retomar o projeto")
    window._add_reminder()
    assert window.reminders.count() == 1
    database = window._scheduler().database
    assert ReminderScheduler(database).list_pending()[0]["message"] == "Retomar o projeto"
    window.reminders.setCurrentRow(0)
    window._cancel_reminder()
    assert ReminderScheduler(database).list_pending() == []
    assert window.reminders.count() == 0


def test_desktop_preferences_and_docks_are_saved_and_motion_can_stop(desktop):
    window, app, _ = desktop
    window.theme_combo.setCurrentIndex(window.theme_combo.findData("daylight"))
    window.font_slider.setValue(17)
    window.motion_check.setChecked(False)
    window.speech_check.setChecked(False)
    window.activity_dock.hide()
    window.close()
    assert window.settings.value("theme") == "daylight"
    assert window.settings.value("font_size", type=int) == 17
    assert not window.companion.timer.isActive()
    assert not window.controller.tts.enabled
    assert window.settings.value("dock_state") is not None
    controller = OverlayWindow(window.controller.loop)
    restored = DesktopWindow(controller, window.store, window.settings)
    restored.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    restored.show()
    app.processEvents()
    assert restored.theme_combo.currentData() == "daylight"
    assert restored.font_slider.value() == 17
    assert not restored.motion_check.isChecked()
    assert not restored.activity_dock.isVisible()
    restored.close()


def test_recollecting_floating_pet_does_not_shutdown_desktop_voice(desktop):
    window, app, _ = desktop
    controller = window.controller
    controller.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    controller.show()
    app.processEvents()
    controller.close()
    assert not controller.isVisible()
    assert controller.tts.shutdown_calls == 0
    assert window.isVisible()


def test_chat_library_searches_message_text_without_like_wildcards(tmp_path):
    store = ChatStore(tmp_path / "chats.db")
    first = store.create()
    second = store.create()
    store.append(first, "user", "Investigar uso de CPU em 100%")
    store.append(second, "user", "Revisar texto")
    assert [c["id"] for c in store.list_chats("CPU")] == [first]
    assert [c["id"] for c in store.list_chats("100%")] == [first]
    store.delete(first)
    assert store.messages(first) == []
    assert [c["id"] for c in store.list_chats()] == [second]
