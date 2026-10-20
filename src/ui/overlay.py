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
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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


class _PromptWorker(QRunnable):
    """Runs the slow model/tool cycle away from Qt's UI thread."""

    def __init__(self, loop: AgentLoop, prompt: str) -> None:
        super().__init__()
        self.loop = loop
        self.prompt = prompt
        self.signals = _PromptSignals()

    def run(self) -> None:
        try:
            self.signals.finished.emit(self.prompt, self.loop.process(self.prompt), None)
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
            result = self.loop.confirm_pending(self.pending_action, True)
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

    def set_message(self, text: str, suggestion: str | None = None) -> None:
        self.lbl_text.setText(text)
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
    mode_hotkey_requested = pyqtSignal()
    screen_stop_requested = pyqtSignal()

    def __init__(self, loop: AgentLoop | None = None) -> None:
        super().__init__()
        self.loop = loop
        self.interaction_parent = self
        self.current_emotion = "idle"
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
        self._center_on_screen_bottom_right()

    def _init_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(6)

        # 1. Balão de fala
        self.bubble = SpeechBubble(self)
        self.main_layout.addWidget(self.bubble)

        # 2. Linha do Avatar e Controles
        avatar_row = QHBoxLayout()
        avatar_row.setSpacing(10)

        # Label onde o sprite pixel art é renderizado
        self.avatar_label = QLabel(self)
        self.avatar_label.setFixedSize(180, 180)
        self.avatar_label.setCursor(Qt.CursorShape.OpenHandCursor)
        self._update_avatar_pixmap()
        avatar_row.addWidget(self.avatar_label)

        # Painel lateral de status e ações rápidas
        side_panel = QVBoxLayout()
        side_panel.setSpacing(6)
        side_panel.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Botão indicador do modo (Assistida / Autônoma)
        self.btn_mode = QPushButton(self)
        self.btn_mode.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode.clicked.connect(self._toggle_mode_clicked)
        self._update_mode_button_style()
        side_panel.addWidget(self.btn_mode)

        # Botão de voz (Push-to-talk / Toggle)
        self.btn_mic = QPushButton("🎙️ Ouvir", self)
        self.btn_mic.setStyleSheet(
            """
            QPushButton {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #0284C7;
                color: #FFFFFF;
            }
            """
        )
        self.btn_mic.clicked.connect(self._on_mic_clicked)
        side_panel.addWidget(self.btn_mic)

        # Botão Grande Sábio (Workspace Sub-Window)
        self.btn_sage = QPushButton("🧙 Sábio", self)
        self.btn_sage.setStyleSheet(
            """
            QPushButton {
                background-color: #1E293B;
                color: #10B981;
                border: 1px solid #059669;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #059669;
                color: #FFFFFF;
            }
            """
        )
        self.btn_sage.clicked.connect(self._toggle_workspace)
        side_panel.addWidget(self.btn_sage)

        from core.updater import updater_supported

        self.btn_update = QPushButton("⟳ Atualizações", self)
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.setToolTip("Verifica uma nova versão e instala com validação e rollback")
        self.btn_update.setVisible(updater_supported())
        self.btn_update.clicked.connect(self._check_for_updates)
        side_panel.addWidget(self.btn_update)

        # Botão Minimizar/Fechar overlay
        self.btn_close = QPushButton("✕ Sair", self)
        self.btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #64748B;
                border: none;
                font-size: 10px;
                padding: 4px;
            }
            QPushButton:hover {
                color: #EF4444;
            }
            """
        )
        self.btn_close.clicked.connect(self.close)
        side_panel.addWidget(self.btn_close)

        avatar_row.addLayout(side_panel)
        avatar_row.addStretch()
        self.main_layout.addLayout(avatar_row)

        # 3. Barra de entrada de texto
        input_container = QFrame(self)
        input_container.setStyleSheet(
            """
            QFrame {
                background-color: rgba(30, 41, 59, 230);
                border: 1px solid #475569;
                border-radius: 8px;
            }
            """
        )
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 4, 8, 4)
        input_layout.setSpacing(6)

        self.txt_input = QLineEdit(input_container)
        self.txt_input.setPlaceholderText("Comando ou mensagem para Nyx...")
        self.txt_input.setStyleSheet(
            """
            QLineEdit {
                background: transparent;
                border: none;
                color: #F8FAFC;
                font-size: 12px;
                padding: 4px;
            }
            QLineEdit:focus {
                outline: none;
            }
            """
        )
        self.txt_input.returnPressed.connect(self._on_send_prompt)
        input_layout.addWidget(self.txt_input)

        btn_send = QPushButton("➔", input_container)
        btn_send.setFixedSize(28, 28)
        btn_send.setStyleSheet(
            """
            QPushButton {
                background-color: #7C3AED;
                color: #FFFFFF;
                border-radius: 6px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #8B5CF6;
            }
            """
        )
        btn_send.clicked.connect(self._on_send_prompt)
        input_layout.addWidget(btn_send)

        self.main_layout.addWidget(input_container)

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
        self.timer.start(550)

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
            self.say("Modo autônomo ativado (30min). Viseira âmbar ligada.", emotion="think")
        else:
            self.loop.deactivate_autonomous(source=source)
            self.current_mode = "assistida"
            self.say("Modo assistido ativo. Pedirei confirmação para ações sensíveis.", emotion="idle")
        self._update_mode_button_style()
        self._update_avatar_pixmap()

    def _stop_screen_control(self) -> None:
        from tools.ui_tool import set_kill_switch

        set_kill_switch(True)
        if self.loop:
            if self.loop.mode_name != "assistida":
                self.loop.deactivate_autonomous(source="ui_hotkey")
                self.current_mode = "assistida"
                self._update_mode_button_style()
            self.loop.audit.log_event("kill_switch_triggered", source="hotkey_ctrl_alt_k")
        self.say("Controle da tela bloqueado. A geração de texto e tarefas já em execução podem continuar.", emotion="error")

    def _center_on_screen_bottom_right(self) -> None:
        from PyQt6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.width() - self.width() - 30
            y = geo.height() - self.height() - 40
            self.move(x, y)

    # ----------------------------------------------------------------------
    # Eventos de Arrastar Janela
    # ----------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
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
        self.set_emotion(emotion)
        self.bubble.set_message(text, suggestion)
        self.message_received.emit("assistant", text)
        if hasattr(self, "tts") and self.tts:
            self.tts.speak(text)

    def _on_voice_state_changed(self, text: str, emotion: str) -> None:
        self.set_emotion(emotion)
        self.bubble.set_message(text, None)

    def listen(self) -> None:
        self.set_emotion("listening")
        self.bubble.set_message("Ouvindo... Fale agora.", None)

    def think(self) -> None:
        self.set_emotion("think")
        self.bubble.set_message("Pensando e analisando melhor plano...", None)

    def show_error(self, err: str) -> None:
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
                conf_result = self.loop.confirm_pending(result.pending_action, False)
                self._show_confirmation_result(conf_result, resp.alternative_suggestion)
                return False
            worker = _ConfirmationWorker(self.loop, result.pending_action)
            worker.signals.finished.connect(self._confirmation_signals.finished)
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
        try:
            if error is not None:
                self.show_error(str(error))
            elif result is not None:
                self._show_confirmation_result(result, None)
        except Exception as exc:
            self.show_error(str(exc))
        finally:
            self._finish_prompt()

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
            if ws.isVisible():
                ws.hide()
            else:
                ws.show()
                ws.raise_()
                ws.activateWindow()
        except Exception as exc:
            log.warning(f"Erro ao alternar Workspace: {exc}")
