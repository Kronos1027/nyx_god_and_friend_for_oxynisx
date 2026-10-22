"""Nyx — ui/overlay.py (Fase 2: Overlay Flutuante & Avatar Pixel Art)

Janela desktop flutuante em PyQt6:
- Frameless + TranslucentBackground + WindowStaysOnTopHint
- Avatar animado em pixel art renderizado via SpriteRenderer (7 estados emocionais)
- Balão de fala cyberpunk com animação e expansão
- Campo de entrada de prompt integrado e botão de microfone
- Toggle seguro de modo de permissão (assistida <-> autônoma)
- Arrastável livremente pela tela
- Conexão direta com o ciclo de decisão do AgentLoop e PermissionDialog
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QPoint, QRunnable, QThreadPool, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.permission_dialog import PermissionDialog
from ui.sprite_renderer import SpriteRenderer

if TYPE_CHECKING:
    from core.agent_loop import AgentLoop

log = logging.getLogger(__name__)


class _PromptSignals(QObject):
    finished = pyqtSignal(str, object, object)
    progress = pyqtSignal(object)


class _PromptWorker(QRunnable):
    """Runs the slow model/tool cycle away from Qt's UI thread."""

    def __init__(self, loop: AgentLoop, prompt: str) -> None:
        super().__init__()
        self.loop = loop
        self.prompt = prompt
        self.signals = _PromptSignals()

    def run(self) -> None:
        try:
            runner = getattr(self.loop, "task_runner", None)
            result = runner.start(self.prompt, self.signals.progress.emit) if runner else self.loop.process(self.prompt)
            self.signals.finished.emit(self.prompt, result, None)
        except Exception as exc:
            self.signals.finished.emit(self.prompt, None, exc)


class _ConfirmationWorker(QRunnable):
    """Executes a user-approved action away from the UI thread."""

    def __init__(self, loop: AgentLoop, pending_action: dict) -> None:
        super().__init__()
        self.loop = loop
        self.pending_action = pending_action
        self.signals = _PromptSignals()

    def run(self) -> None:
        try:
            runner = getattr(self.loop, "task_runner", None)
            result = runner.resume(self.pending_action, True, self.signals.progress.emit) if runner else self.loop.confirm_pending(self.pending_action, True)
            self.signals.finished.emit("", result, None)
        except Exception as exc:
            self.signals.finished.emit("", None, exc)


class _UpdateWorker(QRunnable):
    """Checks GitHub or stages a verified release without blocking the UI."""

    def __init__(self, stage_release: object | None = None) -> None:
        super().__init__()
        self.stage_release = stage_release
        self.signals = _PromptSignals()

    def run(self) -> None:
        try:
            from core.updater import check_for_update, stage_update

            result = stage_update(self.stage_release) if self.stage_release else check_for_update()
            self.signals.finished.emit("stage" if self.stage_release else "check", result, None)
        except Exception as exc:
            self.signals.finished.emit("stage" if self.stage_release else "check", None, exc)


class SpeechBubble(QFrame):
    """Balão de fala cyberpunk para exibição das falas e pensamentos do Nyx."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(15, 23, 42, 235);
                border: 1px solid #334155;
                border-radius: 10px;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self.lbl_speaker = QLabel("Nyx", self)
        self.lbl_speaker.setStyleSheet(
            "color: #A78BFA; font-weight: bold; font-size: 11px; border: none;"
        )
        layout.addWidget(self.lbl_speaker)

        self.lbl_text = QLabel("Olá. Como posso ajudar você hoje?", self)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet(
            "color: #F1F5F9; font-size: 12px; border: none; font-family: 'Segoe UI', sans-serif;"
        )
        layout.addWidget(self.lbl_text)

        self.lbl_suggestion = QLabel("", self)
        self.lbl_suggestion.setWordWrap(True)
        self.lbl_suggestion.setStyleSheet(
            "color: #FDE047; font-size: 11px; font-style: italic; border: none;"
        )
        self.lbl_suggestion.setVisible(False)
        layout.addWidget(self.lbl_suggestion)
        self.setStyleSheet("")
        self.setObjectName("SpeechSurface")
        for label in (self.lbl_speaker, self.lbl_text, self.lbl_suggestion):
            label.setStyleSheet("")
            label.setTextFormat(Qt.TextFormat.PlainText)
        self.lbl_speaker.setObjectName("Eyebrow")
        self.lbl_suggestion.setObjectName("Muted")

    def set_message(self, text: str, suggestion: str | None = None) -> None:
        self.lbl_text.setText(text if len(text) <= 600 else text[:597] + "…")
        if suggestion:
            self.lbl_suggestion.setText(f"💡 Sugestão: {suggestion}")
            self.lbl_suggestion.setVisible(True)
        else:
            self.lbl_suggestion.setVisible(False)


class OverlayWindow(QWidget):
    """Overlay flutuante do agente Nyx com avatar pixel art interativo."""

    # Sinais para integração assíncrona
    prompt_submitted = pyqtSignal(str)
    voice_toggled = pyqtSignal()
    voice_state_changed = pyqtSignal(str, str)  # (texto, emoção)
    message_received = pyqtSignal(str, str)
    processing_changed = pyqtSignal(bool)
    emotion_changed = pyqtSignal(str)
    action_observed = pyqtSignal(object)
    task_progress = pyqtSignal(object)
    mode_hotkey_requested = pyqtSignal()
    screen_stop_requested = pyqtSignal()

    def __init__(self, loop: AgentLoop | None = None) -> None:
        super().__init__()
        self.loop = loop
        self.interaction_parent = self
        self.current_emotion = "idle"
        from ui.pet_routine import PetRoutine

        self._routine = PetRoutine()
        self._routine_look: tuple[float, float] | None = None
        self.current_mode = loop.mode_name if loop else "assistida"
        self.anim_frame = 0
        self._drag_pos = QPoint()
        self._is_dragging = False
        self._processing = False
        self._update_busy = False
        self._update_pool = QThreadPool(self)
        self._update_pool.setMaxThreadCount(1)
        self._prompt_pool = QThreadPool(self)
        self._prompt_pool.setMaxThreadCount(1)
        self._prompt_signals = _PromptSignals()
        self._prompt_signals.finished.connect(self._on_prompt_finished)
        self._confirmation_signals = _PromptSignals()
        self._confirmation_signals.finished.connect(self._on_confirmation_finished)
        self._reminder_scheduler = getattr(loop.registry, "reminder_scheduler", None) if loop else None
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(15_000)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start()

        from audio.tts import TextToSpeech
        self.tts = TextToSpeech()

        self.renderer = SpriteRenderer(scale=5)  # 180x180 px

        # Configurações da Janela
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(360)

        # Conexão de sinais assíncronos
        self.prompt_submitted.connect(self.process_prompt)
        self.voice_state_changed.connect(self._on_voice_state_changed)
        self.mode_hotkey_requested.connect(self._toggle_mode_hotkey)
        self.screen_stop_requested.connect(self._stop_screen_control)

        self._init_ui()
        self._init_timer()
        self.adjustSize()
        self._center_on_screen_bottom_right()

    def _init_ui(self) -> None:
        from ui.desktop_theme import desktop_stylesheet
        self.setStyleSheet(desktop_stylesheet())
        self.motion_enabled = True
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(8)
        self.bubble = SpeechBubble(self)
        self.main_layout.addWidget(self.bubble)
        self.bubble.hide()
        self.avatar_label = QLabel(self)
        self.avatar_label.setFixedSize(180, 180)
        self.avatar_label.setCursor(Qt.CursorShape.OpenHandCursor)
        self.avatar_label.setToolTip("Arraste para mover · botão direito para ações")
        self.avatar_label.setAccessibleName("Oxynisx, companheira animada")
        self.main_layout.addWidget(self.avatar_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._update_avatar_pixmap()
        self.pet_controls = QFrame(self)
        self.pet_controls.setObjectName("ComposerFrame")
        controls = QVBoxLayout(self.pet_controls)
        controls.setContentsMargins(12, 10, 12, 10)
        bar = QHBoxLayout()
        self.btn_mic = QPushButton("Voz")
        self.btn_mic.clicked.connect(self._on_mic_clicked)
        bar.addWidget(self.btn_mic)
        self.btn_sage = QPushButton("Criar ↗")
        self.btn_sage.clicked.connect(self._toggle_workspace)
        bar.addWidget(self.btn_sage)
        self.btn_close = QPushButton("Recolher")
        self.btn_close.clicked.connect(self.close)
        bar.addWidget(self.btn_close)
        controls.addLayout(bar)
        self.txt_input = QLineEdit()
        self.txt_input.setPlaceholderText("Converse com a Nyx…")
        self.txt_input.setAccessibleName("Mensagem para a Nyx flutuante")
        self.txt_input.returnPressed.connect(self._on_send_prompt)
        controls.addWidget(self.txt_input)
        self.main_layout.addWidget(self.pet_controls)
        self.pet_controls.hide()
        self.btn_mode = QPushButton(self)
        self.btn_mode.hide()
        self.btn_mode.clicked.connect(self._toggle_mode_clicked)
        self._update_mode_button_style()
        self.btn_update = QPushButton(self)
        self.btn_update.hide()
        self.btn_update.clicked.connect(self._check_for_updates)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._pet_menu)
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._hide_bubble)

    def _hide_bubble(self) -> None:
        self.bubble.hide()
        self.adjustSize()

    def _pet_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction("Conversar", self._toggle_pet_controls)
        menu.addAction("Ouvir minha voz", self._on_mic_clicked)
        menu.addAction("Espaço de criação", self._toggle_workspace)
        menu.addAction("Abrir Nyx", self._show_desktop)
        menu.addSeparator()
        menu.addAction(self.btn_mode.text(), self._toggle_mode_clicked)
        menu.addAction("Interromper tarefa", self.cancel_task)
        from core.updater import updater_supported
        update = menu.addAction("Verificar atualizações", self._check_for_updates)
        update.setEnabled(updater_supported())
        menu.addAction("Recolher pet", self.hide)
        menu.exec(self.mapToGlobal(position))

    def _show_desktop(self) -> None:
        if self.interaction_parent is not self:
            self.interaction_parent.showNormal()
            self.interaction_parent.raise_()
            self.interaction_parent.activateWindow()

    def _toggle_pet_controls(self) -> None:
        self._note_activity()
        self.pet_controls.setVisible(not self.pet_controls.isVisible())
        if self.pet_controls.isVisible():
            self.txt_input.setFocus()
        self.adjustSize()

    def mouseDoubleClickEvent(self, event) -> None:
        self._note_activity()
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_pet_controls()
            event.accept()

    def set_motion(self, enabled: bool) -> None:
        self.motion_enabled = enabled
        if enabled and self.isVisible():
            self.timer.start(160)
        else:
            self.timer.stop()
        self._update_avatar_pixmap()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "timer") and self.motion_enabled:
            self.timer.start(160)

    def hideEvent(self, event) -> None:
        if hasattr(self, "timer"):
            self.timer.stop()
        super().hideEvent(event)

    def _check_for_updates(self) -> None:
        if self._update_busy:
            return
        self._update_busy = True
        self.btn_update.setEnabled(False)
        self.btn_update.setText("⟳ Verificando...")
        worker = _UpdateWorker()
        worker.signals.finished.connect(self._on_update_worker_finished)
        self._update_pool.start(worker)

    def _stage_update(self, release: object) -> None:
        self._update_busy = True
        self.btn_update.setEnabled(False)
        self.btn_update.setText("⟳ Baixando...")
        worker = _UpdateWorker(stage_release=release)
        worker.signals.finished.connect(self._on_update_worker_finished)
        self._update_pool.start(worker)

    def _finish_update_ui(self) -> None:
        self._update_busy = False
        self.btn_update.setEnabled(True)
        self.btn_update.setText("⟳ Atualizações")

    def _on_update_worker_finished(self, operation: str, result: object, error: object) -> None:
        self._finish_update_ui()
        if error:
            QMessageBox.warning(self, "Atualização da Nyx", f"Não consegui concluir: {error}")
            return
        if operation == "check":
            if result is None:
                QMessageBox.information(self, "Atualização da Nyx", "Você já está na versão mais recente.")
                return
            release = result
            answer = QMessageBox.question(
                self,
                "Atualização disponível",
                f"A versão {release.version} está disponível.\n\n"
                "Deseja baixar e verificar o pacote agora? A Nyx só será fechada depois da verificação.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._stage_update(release)
            return

        payload = result
        answer = QMessageBox.question(
            self,
            "Atualização verificada",
            "O pacote passou na verificação SHA-256 e no exame dos arquivos.\n\n"
            "Deseja fechar a Nyx, instalar a nova versão e reiniciar? Se o autoteste falhar, "
            "o instalador restaura a versão anterior.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            import os

            from PyQt6.QtWidgets import QApplication
            from core.updater import launch_staged_update

            release_version = payload.parent.name
            launch_staged_update(payload, os.getpid(), release_version)
            QApplication.instance().quit()
        except Exception as exc:
            QMessageBox.critical(self, "Atualização da Nyx", f"Não consegui iniciar a instalação: {exc}")

    def _init_timer(self) -> None:
        """Timer de animação periódica para respiração e micro-movimentos."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_animation)
        self.timer.setInterval(160)
        self._routine_timer = QTimer(self)
        self._routine_timer.timeout.connect(self._pet_routine_tick)
        self._routine_timer.setInterval(1000)
        self._routine_timer.start()

    def _pet_routine_tick(self) -> None:
        """Let the companion act on its own while the user is away."""
        if not self.isVisible() or self._processing or self._is_dragging:
            return
        action = self._routine.tick()
        if action.kind == "sleep":
            if self.current_emotion in {"idle", "sleep"}:
                self._routine_look = None
                self.set_emotion("sleep")
        elif action.kind == "look":
            if self.current_emotion == "idle":
                self._routine_look = action.direction
                QTimer.singleShot(int(self._routine.LOOK_HOLD_SECONDS * 1000), self._clear_routine_look)
        elif action.kind == "perk":
            if self.current_emotion == "idle":
                self._routine_look = None
                self.set_emotion("surprised")
                QTimer.singleShot(800, self._settle_routine)

    def _clear_routine_look(self) -> None:
        self._routine_look = None

    def _settle_routine(self) -> None:
        if self.current_emotion == "surprised":
            self.set_emotion("idle")

    def _note_activity(self) -> None:
        """User or assistant activity: wake up and restart the idle countdown."""
        was_asleep = self._routine.notify_activity()
        self._routine_look = None
        if was_asleep and self.current_emotion == "sleep":
            self.set_emotion("idle")

    def _tick_animation(self) -> None:
        if not self.isVisible():
            return
        self.anim_frame = (self.anim_frame + 1) % 120
        self._update_avatar_pixmap()

    def _update_avatar_pixmap(self) -> None:
        pix = self.renderer.get_pixmap(
            emotion=self.current_emotion,
            mode=self.current_mode,
            frame=self.anim_frame,
        )
        if self.current_emotion == "idle" and self.motion_enabled and not self._is_dragging:
            if self._routine_look is not None:
                target = self._routine_look
            else:
                center = self.avatar_label.mapToGlobal(self.avatar_label.rect().center())
                delta = QCursor.pos() - center
                target = (delta.x(), delta.y())
            pix = self.renderer.look_at(target[0], target[1])
        self.avatar_label.setPixmap(pix)

    def _update_mode_button_style(self) -> None:
        if self.current_mode == "autonoma":
            self.btn_mode.setText("⚡ Autônoma")
            self.btn_mode.setStyleSheet(
                """
                QPushButton {
                    background-color: #78350F;
                    color: #FBBF24;
                    border: 1px solid #D97706;
                    border-radius: 6px;
                    padding: 6px 8px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #92400E;
                }
                """
            )
        else:
            self.btn_mode.setText("🛡️ Assistida")
            self.btn_mode.setStyleSheet(
                """
                QPushButton {
                    background-color: #064E3B;
                    color: #34D399;
                    border: 1px solid #059669;
                    border-radius: 6px;
                    padding: 6px 8px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #065F46;
                }
                """
            )

    def _toggle_mode_clicked(self) -> None:
        self._toggle_mode("ui_toggle")

    def _toggle_mode_hotkey(self) -> None:
        self._toggle_mode("ui_hotkey")

    def _toggle_mode(self, source: str) -> None:
        if not self.loop:
            return
        if self.current_mode == "assistida":
            # Ativação autônoma legítima por fonte UI
            self.loop.activate_autonomous(source=source)
            self.current_mode = "autonoma"
            self.say("Modo autônomo ativado por 30 minutos.", emotion="think")
        else:
            self.loop.deactivate_autonomous(source=source)
            self.current_mode = "assistida"
            self.say("Modo assistido ativo. Pedirei confirmação para ações sensíveis.", emotion="idle")
        self._update_mode_button_style()
        self._update_avatar_pixmap()

    def _stop_screen_control(self) -> None:
        from tools.ui_tool import set_kill_switch

        set_kill_switch(True)
        self.cancel_task()
        if self.loop:
            if self.loop.mode_name != "assistida":
                self.loop.deactivate_autonomous(source="ui_hotkey")
                self.current_mode = "assistida"
                self._update_mode_button_style()
            self.loop.audit.log_event("kill_switch_triggered", source="hotkey_ctrl_alt_k")
        self.say("Controle da tela bloqueado e cancelamento solicitado. Uma operação já em curso pode precisar terminar.", emotion="error")

    def _center_on_screen_bottom_right(self) -> None:
        from PyQt6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 30
            y = geo.bottom() - self.height() - 40
            self.move(x, y)

    # ----------------------------------------------------------------------
    # Eventos de Arrastar Janela
    # ----------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._note_activity()
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.avatar_label.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._is_dragging = False
        self.avatar_label.setCursor(Qt.CursorShape.OpenHandCursor)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Encerra TTS de forma limpa ao fechar a janela."""
        if self.interaction_parent is not self and not getattr(self, "_closing_with_desktop", False):
            event.ignore()
            self.hide()
            return
        if hasattr(self, "tts") and self.tts:
            self.cancel_task()
            self.tts.shutdown()
        super().closeEvent(event)

    # ----------------------------------------------------------------------
    # API de Estados e Fala
    # ----------------------------------------------------------------------
    def set_emotion(self, emotion: str) -> None:
        self.current_emotion = emotion
        self._update_avatar_pixmap()
        self.emotion_changed.emit(emotion)

    def say(self, text: str, emotion: str = "talk", suggestion: str | None = None) -> None:
        self._note_activity()
        self.set_emotion(emotion)
        self.bubble.set_message(text, suggestion)
        self.bubble.show()
        self._bubble_timer.start(20_000)
        self.message_received.emit("assistant", text)
        if hasattr(self, "tts") and self.tts:
            self.tts.speak(text)

    def _on_voice_state_changed(self, text: str, emotion: str) -> None:
        self.set_emotion(emotion)
        self.bubble.set_message(text, None)

    def listen(self) -> None:
        self._note_activity()
        self.set_emotion("listening")
        self.bubble.set_message("Ouvindo... Fale agora.", None)

    def think(self) -> None:
        self._note_activity()
        self.set_emotion("think")
        self.bubble.set_message("Pensando e analisando melhor plano...", None)

    def show_error(self, err: str) -> None:
        self._note_activity()
        self.set_emotion("error")
        self.bubble.set_message(f"Erro: {err}", None)
        self.message_received.emit("error", str(err))

    # ----------------------------------------------------------------------
    # Ciclo de Execução do AgentLoop
    # ----------------------------------------------------------------------
    def _on_send_prompt(self) -> None:
        text = self.txt_input.text().strip()
        if not text:
            return
        self.txt_input.clear()
        # Interrompe fala atual antes de processar novo prompt
        if hasattr(self, "tts") and self.tts:
            self.tts.stop_current()
        self.process_prompt(text)

    def _on_mic_clicked(self) -> None:
        if self._processing:
            self.say("Ainda estou trabalhando no pedido anterior.", emotion="think")
            return
        self.voice_toggled.emit()

    def process_prompt(self, user_prompt: str) -> None:
        """Executa um único prompt em segundo plano para manter a UI responsiva."""
        if self._processing:
            self.say("Ainda estou concluindo o pedido anterior. Um instante.", emotion="think")
            return
        self.message_received.emit("user", user_prompt)
        if not self.loop:
            self.say(f"Recebido: {user_prompt} (sem loop ativo)")
            return
        self._processing = True
        self.processing_changed.emit(True)
        self.txt_input.setEnabled(False)
        self.think()
        worker = _PromptWorker(self.loop, user_prompt)
        worker.signals.finished.connect(self._prompt_signals.finished)
        worker.signals.progress.connect(self._on_task_progress)
        self._prompt_pool.start(worker)

    def _on_prompt_finished(self, user_prompt: str, result: object, error: object) -> None:
        if error is not None:
            self.show_error(str(error))
            self._finish_prompt()
            return
        assert result is not None
        keep_processing = False
        try:
            keep_processing = self._render_prompt_result(result)
        except Exception as exc:
            self.show_error(str(exc))
        finally:
            if not keep_processing:
                self._finish_prompt()

    def _render_prompt_result(self, result: object) -> bool:
        self.action_observed.emit(result)
        resp = result.response
        self.current_mode = self.loop.mode_name
        self._update_mode_button_style()

        if result.needs_confirmation and result.pending_action:
            # Dispara diálogo modal de confirmação
            spec = self.loop.registry.spec(result.pending_action.get("type", ""))
            is_destructive = spec.is_destructive_for(result.pending_action.get("params", {})) if spec else False

            self.set_emotion("surprised" if is_destructive else "think")
            approved = PermissionDialog.ask_confirmation(
                result.pending_action,
                prompt=result.confirmation_prompt,
                is_destructive=is_destructive,
                parent=self.interaction_parent,
            )
            if not approved:
                runner = getattr(self.loop, "task_runner", None)
                conf_result = runner.resume(result.pending_action, False) if runner else self.loop.confirm_pending(result.pending_action, False)
                self._show_confirmation_result(conf_result, resp.alternative_suggestion)
                return False
            worker = _ConfirmationWorker(self.loop, result.pending_action)
            worker.signals.finished.connect(self._confirmation_signals.finished)
            worker.signals.progress.connect(self._on_task_progress)
            self._prompt_pool.start(worker)
            return True

        # Resposta normal
        act_type = resp.action.type if (resp and resp.action) else ""
        if act_type == "workspace":
            self._open_workspace_if_needed()

        self.say(
            resp.speech_output,
            emotion=resp.emotion or "talk",
            suggestion=resp.alternative_suggestion,
        )
        return False

    def _on_confirmation_finished(self, _unused: str, result: object, error: object) -> None:
        keep_processing = False
        try:
            if error is not None:
                self.show_error(str(error))
            elif result is not None:
                keep_processing = self._render_prompt_result(result)
        except Exception as exc:
            self.show_error(str(exc))
        finally:
            if not keep_processing:
                self._finish_prompt()

    def _on_task_progress(self, progress: dict) -> None:
        self.task_progress.emit(progress)
        if progress["phase"] == "observed" and progress["tool"] == "workspace":
            self._open_workspace_if_needed()
        if progress["phase"] == "executing":
            self.bubble.set_message(f"Etapa {progress['step']}: {progress['tool']}")
            self.bubble.show()
            self._bubble_timer.start(20_000)

    def cancel_task(self) -> None:
        runner = getattr(self.loop, "task_runner", None)
        if runner and runner.active:
            runner.cancel()
            self.bubble.set_message("Cancelamento solicitado. A operação em curso pode precisar terminar.")

    def _show_confirmation_result(self, result: object, suggestion: str | None) -> None:
        self.action_observed.emit(result)
        act_type = result.response.action.type if (result and result.response.action) else ""
        if act_type == "workspace":
            self._open_workspace_if_needed()
        self.say(
            result.response.speech_output,
            emotion=result.response.emotion or "talk",
            suggestion=suggestion,
        )

    def _finish_prompt(self) -> None:
        self._processing = False
        self.txt_input.setEnabled(True)
        self.processing_changed.emit(False)

    def _check_reminders(self) -> None:
        if not self._reminder_scheduler:
            return
        try:
            due = self._reminder_scheduler.pop_due()
        except Exception as exc:
            log.warning("Falha ao consultar lembretes: %s", exc)
            return
        if due:
            notes = " ".join(item["message"] for item in due)
            suffix = f" Há mais {len(due) - 1} lembrete(s)." if len(due) > 1 else ""
            self.say(f"Lembrete: {notes}{suffix}", emotion="surprised")

    def _open_workspace_if_needed(self) -> None:
        """Abre e traz para o primeiro plano a sub-janela O Grande Sábio."""
        try:
            from ui.workspace_window import WorkspaceWindow
            ws = WorkspaceWindow.get_instance()
            ws.setStyleSheet(self.styleSheet())
            ws.show()
            ws.raise_()
            ws.activateWindow()
        except Exception as exc:
            log.warning(f"Não foi possível abrir sub-janela Workspace: {exc}")

    def _toggle_workspace(self) -> None:
        """Alterna visibilidade da sub-janela O Grande Sábio."""
        try:
            from ui.workspace_window import WorkspaceWindow
            ws = WorkspaceWindow.get_instance()
            ws.setStyleSheet(self.styleSheet())
            if ws.isVisible():
                ws.hide()
            else:
                ws.show()
                ws.raise_()
                ws.activateWindow()
        except Exception as exc:
            log.warning(f"Erro ao alternar Workspace: {exc}")
