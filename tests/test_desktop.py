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


def test_resource_controls_set_real_admission_and_persist(desktop):
    from core.resource_governor import RESOURCE_GOVERNOR, ResourcePolicy
    from core.runtime_budget import GIB, ResourceSnapshot
    window, _, _ = desktop
    try:
        window.ram_reserve_spin.setValue(4096)
        window.vram_reserve_spin.setValue(2048)
        assert window.settings.value("ram_reserve_mib", type=int) == 4096
        assert window.settings.value("vram_reserve_mib", type=int) == 2048
        assert not RESOURCE_GOVERNOR.evaluate(ResourceSnapshot(3 * GIB, None, None)).allowed
    finally:
        RESOURCE_GOVERNOR.configure(ResourcePolicy())


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


def test_pet_motion_controls_focus_and_transparency(desktop):
    window, app, _ = desktop
    pet = window.controller
    pet.show()
    app.processEvents()
    assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert not pet.pet_controls.isVisible()
    assert pet.timer.isActive()
    pet._toggle_pet_controls()
    assert pet.txt_input.isVisible()
    window.motion_check.setChecked(False)
    assert not pet.timer.isActive()
    assert not window.hero_companion.timer.isActive()
    window.motion_check.setChecked(True)
    pet.hide()
    assert not pet.timer.isActive()
    window.focus_button.setChecked(True)
    assert not window.sidebar.isVisible()
    window.focus_button.setChecked(False)
    assert window.sidebar.isVisible()


def test_initiative_emits_one_message_and_setting_persists(desktop):
    window, _, _ = desktop
    args = []
    window._initiative.poll = lambda **kwargs: args.append(kwargs) or "Oi!"
    messages = []
    window.controller.message_received.connect(lambda role, text: messages.append((role, text)))
    window._initiative_tick()
    assert messages == [("assistant", "Oi!")]
    window.initiative_check.setChecked(False)
    assert window.settings.value("conversation_initiative", True, type=bool) is False
    window._initiative_tick()
    assert args[-1]["enabled"] is False


def test_primary_model_setting_is_saved_through_ui(desktop, monkeypatch):
    window, _, _ = desktop
    calls = []
    monkeypatch.setattr("core.ollama_service.save_runtime_config", lambda *args: calls.append(args))
    window.preferred_model.setText("qwen3.5:4b")
    window._save_runtime()
    assert calls[-1][2] == "qwen3.5:4b"
    assert "Reinicie a Nyx" in window.runtime_feedback.text()


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


def test_voice_preferences_apply_and_persist(desktop):
    window, app, _ = desktop
    assert window.voice_combo.count() == 3
    window.voice_combo.setCurrentIndex(window.voice_combo.findData("pm_alex"))
    window.volume_slider.setValue(35)
    window.speech_check.setChecked(False)
    app.processEvents()

    assert window.settings.value("voice") == "pm_alex"
    assert window.settings.value("voice_volume", type=int) == 35
    assert window.settings.value("voice_speed", type=int) == 110

    window._preview_voice()
    assert "Ative" in window.voice_feedback.text()


def test_pet_sleeps_when_idle_and_wakes_on_activity(desktop):
    window, app, _ = desktop
    pet = window.controller
    pet.show()
    app.processEvents()
    pet.set_emotion("idle")

    pet._routine._last_activity -= pet._routine.SLEEP_AFTER_SECONDS + 1
    pet._pet_routine_tick()
    assert pet.current_emotion == "sleep"

    pet._note_activity()
    assert pet.current_emotion == "idle"


def test_pet_does_not_idle_sleep_while_a_prompt_is_running(desktop):
    window, app, _ = desktop
    pet = window.controller
    pet.show()
    app.processEvents()
    pet._processing = True
    pet._routine._last_activity -= pet._routine.SLEEP_AFTER_SECONDS + 1
    try:
        pet._pet_routine_tick()
        assert pet.current_emotion != "sleep"
    finally:
        pet._processing = False


def test_command_palette_filters_and_runs_actions(desktop):
    window, app, _ = desktop
    window.open_palette()
    assert window.palette.isVisible()

    window.palette.input.setText("agenda")
    app.processEvents()
    assert any("Agenda" in entry for entry in window.palette.visible_commands)

    window.palette._run_current()
    app.processEvents()
    assert window.pages.currentIndex() == 1


def test_command_palette_lists_recent_conversations(desktop):
    window, app, _ = desktop
    window.new_chat()
    app.processEvents()

    window.open_palette()
    window.palette.input.setText("Abrir conversa")

    assert any("Abrir conversa" in entry for entry in window.palette.visible_commands)


def test_toast_shows_feedback_and_stops_its_timer(desktop):
    window, app, _ = desktop
    window.notify("Painéis restaurados")
    app.processEvents()

    assert window.toast.isVisible()
    assert window.toast.label.text() == "Painéis restaurados"
    assert window.toast._timer.isActive()

    window.toast.hide_toast()
    assert window.toast._timer.isActive() is False


def test_rail_mode_shrinks_the_library_and_persists(desktop):
    window, app, _ = desktop
    window._set_rail(True)
    app.processEvents()

    assert window._rail is True
    assert window.nav_buttons[0].text() == "◌"
    assert window.chat_list.isVisible() is False
    assert window.settings.value("sidebar_rail", type=bool) is True

    window._set_rail(False)
    app.processEvents()

    assert window.nav_buttons[0].text() == "◌  Conversa"
    assert window.chat_list.isVisible() is True


def test_narrow_window_hides_companion_and_restores_it(desktop):
    window, app, _ = desktop
    window.resize(1000, 800)
    app.processEvents()
    assert window.companion_dock.isVisible() is False

    window.resize(1300, 900)
    app.processEvents()
    assert window.companion_dock.isVisible() is True


def test_typing_indicator_follows_processing(desktop):
    window, app, _ = desktop
    window._on_processing(True)
    app.processEvents()

    assert window._typing_row is not None
    assert window._typing_anim is not None
    assert window._typing_anim.state().name == "Running"

    window._on_processing(False)
    app.processEvents()

    assert window._typing_row is None
    assert window._typing_anim is None


def test_rail_width_animates_instead_of_snapping(desktop):
    window, app, _ = desktop
    window.motion_check.setChecked(True)
    window._set_rail(True)

    deadline = time.monotonic() + 3
    while window.sidebar.width() > 80 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.sidebar.width() <= 80

    window._set_rail(False)
    deadline = time.monotonic() + 3
    while window.sidebar.width() < 240 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window.sidebar.width() >= 240
