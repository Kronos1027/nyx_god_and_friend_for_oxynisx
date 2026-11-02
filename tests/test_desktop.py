import json
import time

import pytest
pytest.importorskip('PyQt6')
from PyQt6.QtCore import QSettings, Qt  # noqa: E402

from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.llm_client import OfflineLLM  # noqa: E402
from core.scheduler import ReminderScheduler  # noqa: E402
from tools.registry import ToolRegistry  # noqa: E402
from ui.chat_store import ChatStore  # noqa: E402
from ui.desktop import DesktopWindow  # noqa: E402
from ui.overlay import OverlayWindow  # noqa: E402


def test_control_center_routes_to_existing_panels(desktop):
    window, _, _ = desktop
    assert window.pages.currentIndex() == 0
    assert window.nav_buttons[0].isChecked()
    for route, title in (("tasks", "Tarefas"), ("memory", "Memória e interesses"),
                         ("privacy", "Observação e iniciativa")):
        window.control_center.route_buttons[route].click()
        assert window.pages.currentIndex() == 3
        assert window.learning_tabs.tabText(window.learning_tabs.currentIndex()) == title
        assert window.learning_section.currentText() == title
    window.control_center.route_buttons["agenda"].click()
    assert window.pages.currentIndex() == 1
    window._open_center_route("chat")
    assert window.pages.currentIndex() == 0


def test_hidden_panel_styling_is_deferred_until_selected(desktop):
    window, app, _ = desktop
    pending = dict(window._deferred_pages)
    assert set(pending) == {1,2,3,4} and window.pages.count() == 5
    assert callable(pending[1]) and callable(pending[4])
    assert all(page.parentWidget() is None for page in (pending[2], pending[3]))
    for index in (2,1,4,3):
        window.set_page(index)
        app.processEvents()
        page = window.pages.currentWidget()
        if not callable(pending[index]):
            assert page is pending[index]
        assert page.isVisible()
        assert index not in window._deferred_pages and window.pages.count() == 5
    window.set_page(0)


def test_resource_profile_is_persisted_and_cannot_change_during_task(desktop):
    from core.resource_profiles import profile_name, select_profile
    window, _, _ = desktop
    try:
        window.resource_profile_combo.setCurrentIndex(window.resource_profile_combo.findData('normal'))
        assert profile_name() == 'normal'
        assert window.settings.value('resource_profile') == 'normal'
        window._busy = True
        window.resource_profile_combo.setCurrentIndex(window.resource_profile_combo.findData('game'))
        assert profile_name() == 'normal'
        assert window.resource_profile_combo.currentData() == 'normal'
        assert window.settings.value('resource_profile') == 'normal'
    finally:
        window._busy = False
        select_profile('conservative')


def test_conversation_deltas_are_plain_text_and_reset_for_new_request(desktop):
    window, _, _ = desktop
    window._on_task_progress({'phase': 'planning', 'step': 1})
    window._on_task_progress({'phase': 'conversation_delta', 'step': 1, 'text': '<b>Olá</b>'})
    assert window._streaming_body.textFormat() == Qt.TextFormat.PlainText
    assert window._streaming_body.text() == '<b>Olá</b>'
    window._on_task_progress({'phase': 'planning', 'step': 1})
    window._on_task_progress({'phase': 'conversation_delta', 'step': 1, 'text': 'Bom dia'})
    assert window._streaming_body.text() == 'Bom dia'
    count = len(window._cards)
    window._on_message('assistant', 'Bom dia')
    assert window._streaming_card is None
    assert len(window._cards) == count + 1


def test_model_degradation_notice_is_visible_and_not_only_a_tooltip(desktop):
    window, app, llm = desktop
    llm.runtime_notice = 'Usando modelo menor instalado por pressão de memória; principal preservado.'
    window._refresh_status()
    app.processEvents()
    assert window.runtime_notice_banner.isVisible()
    assert window.runtime_notice_banner.text() == llm.runtime_notice
    assert llm.runtime_notice in window.model_badge.toolTip()


def test_agora_clears_finished_step_instead_of_showing_stale_work(desktop):
    window, _, _ = desktop
    window.agora.progress({'phase':'executing','step':2,'tool':'ui_action'})
    assert window.agora.stepper.text()
    window.agora.set_busy(False)
    assert not window.agora.stepper.text() and not window.agora.cancel.isEnabled()


def test_agora_has_opt_in_sensors_and_rejects_late_private_readings(desktop):
    from core.presence_sensors import PresenceMonitor
    window, app, _ = desktop
    for sensor in ('active_window', 'process_inventory', 'media', 'games'):
        assert not window.sensor_checks[sensor].isChecked()
    window._refresh_presence()
    assert window._presence is None
    window.sensor_checks['active_window'].setChecked(True)
    window._presence = PresenceMonitor(window._context)
    window._presence.resume()
    reading = {'generation': 0, 'observed_at': time.monotonic(),
               'fields': {'window': {'status': 'ok', 'text': 'Fixture title'}}}
    window._presence_done(reading)
    assert window.agora.fields['window'].text() == 'Fixture title'
    window.private_button.setChecked(True)
    app.processEvents()
    window._presence_done(reading)
    assert window._context.permissions()['active_window']
    assert 'Fixture title' not in window.agora.fields['window'].text()
    assert 'Privado' in window.agora.fields['window'].text()
    window.private_button.setChecked(False)
    window._presence_done(reading)
    assert 'Fixture title' not in window.agora.fields['window'].text()


def test_memory_diagnostics_opens_without_process_enumeration(desktop, monkeypatch):
    from ui.resource_diagnostics import ResourceDiagnosticsDialog
    requests = []
    monkeypatch.setattr(ResourceDiagnosticsDialog, 'refresh', lambda self, include=False: requests.append(include))
    window, _, _ = desktop
    window.memory_diagnostic_button.click()
    assert window._resource_diagnostic_dialog.isVisible()
    assert requests == [False]


def test_public_cloud_backup_is_disabled_but_local_timer_remains(desktop):
    window, _, _ = desktop
    assert not window.cloud_backup_check.isChecked()
    assert not window.cloud_backup_check.isEnabled()
    assert not window.settings.value('cloud_backup', True, type=bool)
    assert window.backup_timer.isActive()


def test_saved_task_returns_to_its_original_conversation(desktop, monkeypatch):
    from types import SimpleNamespace
    from PyQt6.QtWidgets import QListWidgetItem
    window, _, _ = desktop
    origin = window.chat_id
    window.store.append(origin, "user", "Contexto da conversa original")
    window.new_chat()
    assert window.chat_id != origin
    task = {"chat_id": origin}
    monkeypatch.setattr(window, "_task_journal", lambda: SimpleNamespace(get=lambda identity: task))
    item = QListWidgetItem("Tarefa pausada")
    item.setData(Qt.ItemDataRole.UserRole, "saved-task")
    window.task_history.addItem(item)
    window.task_history.setCurrentItem(item)
    called = []
    monkeypatch.setattr(window.controller, "continue_task", lambda identity: called.append((identity, window.chat_id)))
    window._continue_saved_task()
    assert called == [("saved-task", origin)]
    assert window.controller.loop.conversation_id == origin
    assert window.controller.loop.history[-1]["content"] == "Contexto da conversa original"
    task.clear()
    window._continue_saved_task()
    assert len(called) == 1  # Legacy/unbound records must not adopt an unrelated chat.


def test_global_stop_blocks_actions_and_resume_requires_user_control(desktop, monkeypatch):
    window, app, _ = desktop
    control = window.controller.loop.registry.control
    window.emergency_button.click()
    assert control.is_cancelled()
    assert "interrompidas" in window.control_center.status.text()
    assert window.hud_resume_button.isVisible()
    monkeypatch.setattr("psutil.virtual_memory", lambda: (_ for _ in ()).throw(OSError("fixture")))
    window._refresh_status()
    assert "interrompidas" in window.control_center.status.text()
    assert window.control_center.values["resources"].text() == "Indisponível"
    window.hud_resume_button.click()
    app.processEvents()
    assert not control.is_cancelled()


def test_center_activity_is_bounded(desktop):
    window, _, _ = desktop
    for index in range(12):
        window._add_activity(f"Owned UI event {index}")
    assert window.control_center.activity.count() == 6
    assert "11" in window.control_center.activity.item(0).text()


def test_recovery_progress_is_visible_without_claiming_execution(desktop):
    window, _, _ = desktop
    window._on_task_progress({"phase": "recovering", "step": 2, "task_id": "owned"})
    assert "gerando novamente" in window.busy_label.text()
    assert "não foi executada" in window.control_center.activity.item(0).text()


def test_compact_layout_keeps_global_controls_visible(desktop):
    window, app, _ = desktop
    window.resize(920, 680)
    app.processEvents()
    assert window.model_badge.isVisible()  # Model remains in the compact HUD strip.
    assert not window.activity_dock.isVisible()
    assert window.emergency_button.isVisible()
    assert window.page_title.width() > 100
    assert window.page_title.geometry().right() < window.panel_button.geometry().left()
    window.resize(1320, 860)
    app.processEvents()
    assert window.model_badge.isVisible()
    assert not window.activity_dock.isVisible()  # Activity is an optional drawer in HUD.


def test_center_opens_projects_and_real_telemetry(desktop, tmp_path, monkeypatch):
    from ui.workspace_window import WorkspaceWindow
    window, app, _ = desktop
    studio = WorkspaceWindow(project_directory=tmp_path / "studio", package_directory=tmp_path / "packages")
    studio.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    monkeypatch.setattr(WorkspaceWindow, "_instance", studio)
    try:
        window.control_center.route_buttons["studio"].click()
        assert studio.tabs.currentWidget() is studio.projects_panel
        window.theme_combo.setCurrentIndex(window.theme_combo.findData("daylight"))
        assert studio.styleSheet() == window.styleSheet()
        _wait(app, lambda: studio.projects_panel.job is None, timeout=10)
        window.control_center.route_buttons["performance"].click()
        assert studio.tabs.currentIndex() == 3
        _wait(app, lambda: studio.telemetry_job is None, timeout=10)
        assert "atualizada" in studio.lbl_status.text()
        assert "CPU" in studio.lbl_hw_info.text()
    finally:
        _wait(app, lambda: studio.telemetry_job is None and studio.projects_panel.job is None, timeout=10)
        studio.close()


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


def test_social_controls_are_connected_to_persistence(desktop):
    window, _, _ = desktop
    window.sensor_checks["own_tasks"].setChecked(False)
    assert not window._context.permissions()["own_tasks"]
    window.interest_topic.setText("astronomia")
    window._save_interest()
    assert window._interests.records()[0]["topic"] == "astronomia"
    window.interest_list.setCurrentRow(0)
    window._select_interest(window.interest_list.currentItem())
    window.interest_topic.setText("música")
    window._save_interest()
    assert [r["topic"] for r in window._interests.records()] == ["música"]
    window.interest_list.setCurrentRow(0)
    window._delete_interest()
    assert window._interests.records() == []
    window.interests_enabled_check.setChecked(False)
    assert not window._interests.enabled


def test_emergency_hotkey_blocks_tools_until_manual_resume(desktop, monkeypatch):
    from core.operation_control import OperationCancelled
    window, _, _ = desktop
    pet = window.controller
    monkeypatch.setattr(pet, "say", lambda *a, **k: None)
    pet._stop_screen_control()
    with pytest.raises(OperationCancelled):
        pet.loop.registry.control.begin()
    pet.resume_tools()
    assert not pet.loop.registry.control.is_cancelled()


def test_browser_preferences_authorize_only_separate_profile(desktop):
    from tools.browser_tool import BrowserSession
    window, _, _ = desktop
    browser = BrowserSession()
    window.controller.loop.registry.browser_session = browser
    window.browser_persist_check.setChecked(False)
    window._update_browser_preferences()
    assert not browser.headless and browser.persistent_profile is None
    window.browser_persist_check.setChecked(True)
    assert browser.persistent_profile == window.store.database.parent / "browser_profiles" / "default"
    assert window.settings.value("browser_persistent", type=bool)
    assert not browser.started
    window.browser_persist_check.setChecked(False)
    assert browser.persistent_profile is None


def test_failed_task_generates_context_and_verified_retry_resolves(desktop):
    window, _, _ = desktop
    event = {"phase": "observed", "task_id": "test", "step": 1, "tool": "read_file", "ok": False}
    window._on_task_progress(event)
    assert len(window._pending_task_events) == 1
    window._on_task_progress(event | {"ok": True, "verified": True})
    assert not window._pending_task_events


def test_task_panel_continues_paused_checkpoint_and_updates_budget(desktop, tmp_path):
    from core.task_journal import TaskJournal
    from core.task_runner import TaskRunner
    from tools.registry import ToolResult, ToolSpec
    window, app, llm = desktop
    journal = TaskJournal(tmp_path / "tasks.db")
    loop = window.controller.loop
    runner = loop.task_runner = TaskRunner(loop, journal=journal)
    loop.registry.register(ToolSpec("read_file", "fixture"), lambda p: ToolResult(True, "observed"))
    llm.queue(json.dumps({"emotion": "idle", "action": {"type": "read_file", "params": {}}, "speech_output": "Lendo"}))
    try:
        runner.start("Leia e relate", lambda event: runner.pause() if event["phase"] == "observed" else None)
        identity = runner.task_id
        window._refresh_tasks()
        window.task_history.setCurrentRow(0)
        window._show_saved_task(window.task_history.currentItem())
        assert "Etapas: 1 de 6" in window.task_preview.toPlainText()
        window.task_budget_combo.setCurrentIndex(1)
        assert runner.default_budget == (12, 1800)
        assert journal.get(identity)["max_actions"] == 6
        llm.queue(json.dumps({"emotion": "idle", "action": {"type": "none", "params": {}}, "speech_output": "Resultado: observed"}))
        window._continue_saved_task()
        _wait(app, lambda: not window._busy)
        assert journal.get(identity)["state"] == "PLANNING_FINISHED"
        assert len(journal.get(identity)["steps"]) == 1
        assert "Resposta concluída" in window.task_history.item(0).text()
    finally:
        journal.close()
        loop.task_runner = None


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
def desktop(tmp_path, monkeypatch, qapp):
    app = qapp
    monkeypatch.setattr("audio.tts.TextToSpeech", SilentVoice)
    registry = ToolRegistry()
    registry.reminder_scheduler = ReminderScheduler(tmp_path / "reminders.db")
    llm = OfflineLLM()
    loop = AgentLoop(llm, registry, AuditLogger(tmp_path / "logs", session_id="ui-test"))
    controller = OverlayWindow(loop)
    settings = QSettings(str(tmp_path / "desktop.ini"), QSettings.Format.IniFormat)
    settings.setValue('resource_profile', 'conservative')  # Explicit preference, independent of the test host.
    window = DesktopWindow(controller, ChatStore(tmp_path / "chats.db"), settings)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    app.processEvents()
    yield window, app, llm
    window.close()
    app.processEvents()
    from core.resource_profiles import select_profile
    select_profile('conservative')


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
    assert window.agenda_empty.isVisible()
    assert not window.cancel_reminder_button.isEnabled()
    window.reminder_text.setText("Retomar o projeto")
    window._add_reminder()
    assert window.reminders.count() == 1
    assert not window.agenda_empty.isVisible()
    database = window._scheduler().database
    assert ReminderScheduler(database).list_pending()[0]["message"] == "Retomar o projeto"
    window.reminders.setCurrentRow(0)
    assert window.cancel_reminder_button.isEnabled()
    window.cancel_reminder_button.click()
    assert ReminderScheduler(database).list_pending() == []
    assert window.reminders.count() == 0
    assert window.agenda_empty.isVisible()
    assert not window.cancel_reminder_button.isEnabled()


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
    assert window.nav_buttons[0].text() == ''
    assert not window.nav_buttons[0].icon().isNull()
    assert window.nav_buttons[0].accessibleName() == 'Conversa'
    assert window.chat_list.isVisible() is False
    assert window.settings.value("sidebar_rail", type=bool) is True

    window._set_rail(False)
    app.processEvents()

    assert window.nav_buttons[0].text() == 'Conversa'
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
    while window.sidebar.width() < 195 and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert 195 <= window.sidebar.width() <= 205


def test_hud_private_pauses_without_deleting_and_restores_prior_choices(desktop):
    window, _, _ = desktop
    window.speech_check.setChecked(False)
    window.initiative_check.setChecked(True)
    permissions = window._context.permissions()
    event = window._context.emit('own_tasks','task_complete','owned','Fixture')
    window.private_button.setChecked(True)
    assert window._context.is_paused and not window.initiative_check.isChecked()
    assert not window.speech_check.isChecked()
    assert window._context.permissions() == permissions
    with window._context.connect() as database:
        assert database.execute('SELECT id FROM context_events WHERE id=?',(event,)).fetchone()
    window.private_button.setChecked(False)
    assert not window._context.is_paused and window.initiative_check.isChecked()
    assert not window.speech_check.isChecked()


def test_inline_confirmation_is_exact_and_denies_changed_payload(desktop):
    from PyQt6.QtCore import QTimer
    window, _, _ = desktop
    pending = {'type':'write_file','params':{'text':'ação exata 🌙','path':'fixture.txt'}}
    def mutate_then_click():
        assert window._pending_confirm_card.pending_action['params']['text'] == 'ação exata 🌙'
        pending['params']['text'] = 'changed'
        window._pending_confirm_card.btn_approve.click()
    QTimer.singleShot(0,mutate_then_click)
    assert not window.request_confirmation(pending)


def test_inline_confirmation_needs_explicit_click_and_stop_denies(desktop):
    from PyQt6.QtCore import QTimer
    window, _, _ = desktop
    pending = {'type':'ui_action','params':{'action':'open_app','app':'Fixture'}}
    QTimer.singleShot(0,lambda:window._pending_confirm_card.btn_approve.click())
    assert window.request_confirmation(pending)
    QTimer.singleShot(0,window._emergency_stop)
    assert not window.request_confirmation(pending)
    assert window.controller.loop.registry.control.is_cancelled()


def test_action_receipt_separates_confirmed_window_from_focus_denial(qapp):
    from ui.hud.action_card import ActionCard
    from PyQt6.QtWidgets import QLabel
    card = ActionCard({'step':1,'tool':'ui_action','ok':True,'verified':True},
                      {'params':{'action':'open_app'},'focus_verified':False})
    labels = [label.text() for label in card.findChildren(QLabel)]
    assert 'Janela confirmada' in labels
    assert 'Aberto, mas não foi possível trazer para frente' in labels
    card.deleteLater()


def test_hud_hiding_stops_visual_polling_and_keeps_backup_service(desktop):
    window, app, _ = desktop
    window.hide()
    app.processEvents()
    assert not window.telemetry_timer.isActive()
    assert not window.research_timer.isActive()
    assert not window.initiative_timer.isActive()
    assert window.backup_timer.isActive()  # Backup policy is outside the HUD redesign.


def test_reduced_motion_keeps_typing_indicator_static(desktop):
    window, app, _ = desktop
    window.motion_check.setChecked(False)
    window._on_processing(True)
    app.processEvents()
    assert window._typing_row is not None
    assert window._typing_anim.state().name == 'Stopped'
    window._on_processing(False)


def test_resolved_confirmation_cards_keep_minimum_layout_height(desktop):
    from PyQt6.QtCore import QTimer
    window, app, _ = desktop
    pending = {'type':'ui_action','params':{'action':'open_app','app':'Fixture'}}
    for _ in range(3):
        QTimer.singleShot(0,lambda:window._pending_confirm_card.btn_deny.click())
        assert not window.request_confirmation(pending)
    app.processEvents()
    from ui.hud.confirm_card import ConfirmCard
    for card in window.feed.findChildren(ConfirmCard):
        assert card.height() >= card.minimumSizeHint().height()


def test_palette_fuzzy_typo_finds_existing_action(desktop):
    window, app, _ = desktop
    window.open_palette()
    window.palette.input.setText('agnda')
    app.processEvents()
    assert any('Agenda' in entry for entry in window.palette.visible_commands)
    window.palette._run_current()
    assert window.pages.currentIndex() == 1
