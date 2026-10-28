"""Native conversation workspace with persistent chats and movable panels."""

from __future__ import annotations

import logging
import threading
import shutil
import time
from datetime import datetime

from PyQt6.QtCore import (
    QDateTime, QEasingCurve, QPropertyAnimation, QRectF, QSettings, Qt, QTimer, QUrl,
    QVariantAnimation, pyqtSignal,
)
from PyQt6.QtGui import QCursor, QColor, QDesktopServices, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDockWidget, QFormLayout,
    QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSlider, QStackedWidget, QTextBrowser, QTextEdit,
    QToolButton, QVBoxLayout, QWidget, QSizePolicy, QSpacerItem, QTabWidget, QSpinBox,
)

from app_paths import user_data_dir
from ui.chat_store import ChatStore
from ui.command_palette import CommandPalette
from ui.desktop_theme import ACCENTS, desktop_stylesheet
from ui.sprite_renderer import SpriteRenderer
from ui.toast import Toast

log = logging.getLogger(__name__)


class Composer(QTextEdit):
    submitted = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
        else:
            super().keyPressEvent(event)


class SafeMarkdown(QTextBrowser):
    def loadResource(self, resource_type: int, name: QUrl):
        # Generated Markdown cannot read local images or fetch remote media.
        return None


class MessageCard(QFrame):
    def __init__(self, role: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName({"user": "UserCard", "error": "ErrorCard"}.get(role, "AssistantCard"))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        header = QHBoxLayout()
        label = QLabel({"user": "VOCÊ", "error": "NYX · AVISO"}.get(role, "NYX"))
        label.setObjectName("MessageRole")
        header.addWidget(label)
        header.addStretch()
        copy = QPushButton("Copiar")
        copy.setObjectName("Quiet")
        copy.setAccessibleName("Copiar mensagem")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(text))
        header.addWidget(copy)
        layout.addLayout(header)
        self.body = SafeMarkdown(self)
        self.body.setObjectName("MessageBody")
        self.body.setOpenLinks(False)
        self.body.anchorClicked.connect(self._open_link)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setMarkdown(text[:100_000])
        self.body.document().setDocumentMargin(0)
        layout.addWidget(self.body)
        self.setMinimumWidth(150)
        if role == "user":
            self.setMaximumWidth(740)

    @staticmethod
    def _open_link(url: QUrl) -> None:
        if url.scheme() in {"https", "http"}:
            QDesktopServices.openUrl(url)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.body.document().setTextWidth(max(120, self.body.viewport().width()))
        self.body.setFixedHeight(min(12_000, max(35, int(self.body.document().size().height()) + 12)))


class CompanionStage(QWidget):
    """Small animated native canvas. Its timer stops when hidden."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(165)
        self.renderer = SpriteRenderer(scale=3)
        self.emotion = "idle"
        self.mode = "assistida"
        self.accent = QColor(ACCENTS["violet"])
        self.frame = 0
        self.motion = True
        self._reaction = False
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._tick)
        self.setToolTip("Sua companhia local · clique para cumprimentar")
        self.setAccessibleName("Mascote Nyx animado")

    def _tick(self) -> None:
        if self.window().isMinimized():
            return
        self.frame = (self.frame + 1) % 48
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.motion:
            self.timer.start()

    def hideEvent(self, event) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def set_motion(self, enabled: bool) -> None:
        self.motion = enabled
        if enabled and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def mousePressEvent(self, event) -> None:
        self._reaction = True
        self.update()
        QTimer.singleShot(900, self._restore_emotion)

    def _restore_emotion(self) -> None:
        self._reaction = False
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(self.width() / 2 - 68, self.height() / 2 - 68, 136, 136)
        faint = QColor(self.accent)
        faint.setAlpha(35)
        painter.setPen(QPen(faint, 1))
        painter.drawEllipse(ring)
        painter.setPen(QPen(self.accent, 2))
        angle = (self.frame * 7 if self.motion else 40) * 16
        painter.drawArc(ring, angle, 74 * 16)
        painter.drawArc(ring.adjusted(7, 7, -7, -7), -angle, 38 * 16)
        pixmap = self.renderer.get_pixmap("waving" if self._reaction else self.emotion, self.mode, self.frame)
        if self.emotion == "idle" and not self._reaction and self.motion:
            delta = QCursor.pos() - self.mapToGlobal(self.rect().center())
            pixmap = self.renderer.look_at(delta.x(), delta.y())
        painter.drawPixmap((self.width() - pixmap.width()) // 2, (self.height() - pixmap.height()) // 2, pixmap)


class DesktopWindow(QMainWindow):
    shutdown_requested = pyqtSignal()
    backup_finished = pyqtSignal(str)
    research_finished = pyqtSignal(object)

    def __init__(self, controller, store: ChatStore | None = None, settings: QSettings | None = None) -> None:
        super().__init__()
        self.setObjectName("NyxDesktop")
        self.setWindowTitle("Nyx — sua companhia de trabalho")
        self.resize(1320, 860)
        self.setMinimumSize(920, 640)
        self.controller = controller
        self.controller.interaction_parent = self
        self.controller.btn_close.setText("✕ Recolher")
        self.store = store or ChatStore(user_data_dir() / "data" / "nyx_chats.db")
        self.settings = settings or QSettings(str(user_data_dir() / "data" / "desktop.ini"), QSettings.Format.IniFormat)
        self.toast = Toast(self)
        self.palette = CommandPalette(self)
        self._rail = False
        self._companion_auto_hidden = False
        self._activity_auto_hidden = False
        self.chat_id = ""
        self._busy = False
        self._research_busy = False
        self._closing = False
        self._research_cancel = threading.Event()
        self._last_interaction = time.monotonic()
        from core.context_awareness import ContextAwarenessEngine
        from core.initiative import ProactiveInteractionEngine
        from core.interests import InterestEngine
        self._context = ContextAwarenessEngine(self.store.database.with_name("nyx_context.db"))
        from core.process_events import AuthorizedProcessSensor
        self._process_sensor = AuthorizedProcessSensor(self._context)
        self._initiative = ProactiveInteractionEngine(self._context)
        memory = getattr(self.controller.loop, "memory", None)
        self._interests = memory.interests if memory else InterestEngine(self._context.database)
        self._initiative.interests = self._interests
        self._pending_task_events = {}
        self._pressure_event = None
        self._cards: list[QWidget] = []
        self._animation: QPropertyAnimation | None = None
        self._animated_page: QWidget | None = None
        self._typing_row: QWidget | None = None
        self._typing_anim: QPropertyAnimation | None = None
        self._rail_anim: QVariantAnimation | None = None
        self._build_center()
        self._build_sidebar()
        self._build_companion()
        self._build_activity()
        self._build_menu()
        self._connect_controller()
        self._apply_preferences()
        self._restore_layout()
        self._set_rail(bool(self.settings.value("sidebar_rail", False, type=bool)))
        self._reload_chats()
        chats = self.store.list_chats()
        selected = str(self.settings.value("last_chat", ""))
        self.activate_chat(selected if any(c["id"] == selected for c in chats) else (chats[0]["id"] if chats else self.store.create()))
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.setInterval(2000)
        self.telemetry_timer.timeout.connect(self._refresh_status)
        self.telemetry_timer.start()
        self._refresh_status()
        self._backup_busy = False
        self.backup_finished.connect(self._backup_done)
        self.backup_timer = QTimer(self)
        self.backup_timer.setInterval(30 * 60 * 1000)
        self.backup_timer.timeout.connect(self._start_backup)
        self.backup_timer.start()
        self.research_finished.connect(self._research_done)
        self.research_timer = QTimer(self)
        self.research_timer.setInterval(30_000)
        self.research_timer.timeout.connect(self._research_tick)
        self.research_timer.start()
        self.initiative_timer = QTimer(self)
        self.initiative_timer.setInterval(30_000)
        self.initiative_timer.timeout.connect(self._initiative_tick)
        self.initiative_timer.start()
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_chat)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.open_palette)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.search.setFocus())
        QShortcut(QKeySequence("Ctrl+B"), self, activated=lambda: self._set_rail(not self._rail))
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.set_page(4))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.set_page(0))
        self.set_page(4)

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _slider_with_readout(slider: QSlider) -> tuple[QWidget, QLabel]:
        """Put a slider and a live percentage readout on the same form row."""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        readout = QLabel(f"{slider.value()}%")
        readout.setMinimumWidth(44)
        readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(slider, 1)
        row.addWidget(readout)
        slider.valueChanged.connect(lambda value: readout.setText(f"{value}%"))
        return holder, readout

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("DesktopPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        return page, layout

    def _build_center(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("TopBar")
        header = QHBoxLayout(bar)
        header.setContentsMargins(24, 15, 24, 15)
        self.page_title = QLabel("Conversa")
        self.page_title.setObjectName("PageTitle")
        self.page_title.setMinimumWidth(0)
        self.page_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.page_title, 1)
        self.model_badge = QLabel(self._model_name())
        self.model_badge.setObjectName("Badge")
        self.model_badge.setToolTip(getattr(getattr(getattr(self.controller, "loop", None), "llm", None), "unavailable_reason", "Modelo executado neste computador."))
        header.addWidget(self.model_badge)
        self.panel_button = QToolButton()
        self.panel_button.setText("Painéis  ▾")
        self.panel_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        header.addWidget(self.panel_button)
        self.focus_button = QPushButton("Foco")
        self.focus_button.setCheckable(True)
        self.focus_button.setToolTip("Recolher painéis para ampliar a conversa")
        self.focus_button.toggled.connect(self._toggle_focus)
        header.addWidget(self.focus_button)
        self.emergency_button = QPushButton("Parar ações")
        self.emergency_button.setObjectName("Danger")
        self.emergency_button.setAccessibleName("Interromper todas as ações da Nyx")
        self.emergency_button.clicked.connect(self._emergency_stop)
        header.addWidget(self.emergency_button)
        root.addWidget(bar)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self._build_chat_page()
        self._build_agenda_page()
        self._build_settings_page()
        self._build_evolution_page()
        from ui.control_center import ControlCenter
        self.control_center = ControlCenter()
        self.control_center.requested.connect(self._open_center_route)
        self.pages.addWidget(self.control_center)

    def _toggle_focus(self, enabled: bool) -> None:
        docks = (self.sidebar, self.companion_dock, self.activity_dock)
        if enabled:
            self._focus_visibility = [dock.isVisible() for dock in docks]
            for dock in docks:
                dock.hide()
        else:
            for dock, visible in zip(docks, getattr(self, "_focus_visibility", [True] * 3), strict=True):
                dock.setVisible(visible)

    def _emergency_stop(self):
        loop = self.controller.loop
        loop.registry.control.stop(emergency=True)
        self.controller.cancel_task()
        if loop.mode_name != "assistida":
            loop.deactivate_autonomous(source="desktop_emergency_button")
            self.controller.current_mode = "assistida"
            self.controller._update_mode_button_style()
        loop.audit.log_event("kill_switch_triggered", source="desktop_emergency_button")
        self._add_activity("Interrupção geral solicitada; operações em curso podem precisar terminar.")
        self._refresh_status()

    def _open_center_route(self, route):
        if route == "chat":
            self.set_page(0)
            self.composer.setFocus()
        elif route == "agenda":
            self.set_page(1)
        elif route == "resume":
            self.controller.resume_tools()
            self._refresh_status()
        elif route in {"tasks", "memory", "privacy"}:
            title = {"tasks": "Tarefas", "memory": "Memória e interesses", "privacy": "Observação e iniciativa"}[route]
            self.set_page(3)
            for index in range(self.learning_tabs.count()):
                if self.learning_tabs.tabText(index) == title:
                    self.learning_tabs.setCurrentIndex(index)
                    break
        elif route in {"studio", "performance"}:
            from ui.workspace_window import WorkspaceWindow
            window = WorkspaceWindow.get_instance()
            window.setStyleSheet(self.styleSheet())
            if route == "performance":
                window.tabs.setCurrentIndex(3)
                window.refresh_telemetry()
            else:
                window.tabs.setCurrentIndex(4)
            window.show()
            window.raise_()
            window.activateWindow()

    def _refresh_center_tasks(self):
        journal = self._task_journal()
        if journal is None:
            self.control_center.values["tasks"].setText("Indisponível")
            self.control_center.notes["tasks"].setText("Histórico não conectado nesta sessão")
            return
        try:
            tasks = journal.list()
            pending = sum(task["state"] in {"PAUSED", "WAITING_REVIEW", "RESOURCE_PRESSURE", "WAITING_USER", "FAILED"}
                          for task in tasks)
            self.control_center.set_tasks(len(tasks), pending)
        except Exception:
            log.debug("Task overview unavailable", exc_info=True)
            self.control_center.values["tasks"].setText("Indisponível")
            self.control_center.notes["tasks"].setText("Não foi possível consultar o histórico")

    def _model_name(self) -> str:
        llm = getattr(getattr(self.controller, "loop", None), "llm", None)
        if getattr(llm, "unavailable_reason", ""):
            return "Sem modelo disponível"
        model = getattr(llm, "model", None)
        return f"Local · {model}" if model else ("Modo de demonstração" if type(llm).__name__ == "OfflineLLM" else "Modelo local")

    def _build_chat_page(self) -> None:
        page, layout = self._page()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.feed = QWidget()
        self.feed.setObjectName("MessageFeed")
        self.feed_layout = QVBoxLayout(self.feed)
        self.feed_layout.setContentsMargins(4, 10, 4, 15)
        self.feed_layout.setSpacing(18)
        self.hero = QWidget()
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 30, 24, 25)
        self.hero_companion = CompanionStage()
        self.hero_companion.setFixedHeight(170)
        hero_layout.addWidget(self.hero_companion)
        eyebrow = QLabel("NYX / OXYNISX")
        eyebrow.setObjectName("Eyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(eyebrow)
        title = QLabel("O que vamos fazer juntos?")
        title.setObjectName("HeroTitle")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(title)
        hero_layout.addWidget(self._muted("Converse, pesquise ou transforme uma ideia em trabalho.\nA Nyx usa os modelos e as ferramentas disponíveis no seu computador."))
        hero_layout.addSpacing(22)
        suggestions = (
            ("◈  Entender meu computador", "Verifique o uso de CPU, RAM e GPU deste computador e explique o estado atual."),
            ("⌕  Explorar uma ideia", "Quero pesquisar uma ideia. Primeiro me ajude a definir a pergunta e o que precisamos descobrir."),
            ("✧  Trabalhar com microagentes", "Use dois microagentes para investigar separadamente o estado do sistema e os arquivos de trabalho permitidos."),
        )
        for caption, prompt in suggestions:
            button = QPushButton(caption)
            button.setObjectName("Suggestion")
            button.clicked.connect(lambda checked=False, text=prompt: self._prefill(text))
            hero_layout.addWidget(button)
        self.feed_layout.addWidget(self.hero)
        self.feed_layout.addStretch()
        self.scroll.setWidget(self.feed)
        layout.addWidget(self.scroll, 1)
        self.busy_label = self._muted("A Nyx está trabalhando no seu pedido…")
        self.busy_label.hide()
        layout.addWidget(self.busy_label)
        composer_frame = QFrame()
        composer_frame.setObjectName("ComposerFrame")
        composition = QVBoxLayout(composer_frame)
        composition.setContentsMargins(14, 10, 14, 12)
        self.composer = Composer()
        self.composer.setObjectName("Composer")
        self.composer.setPlaceholderText("Pergunte à Nyx ou descreva o que quer fazer…")
        self.composer.setAccessibleName("Mensagem para a Nyx")
        self.composer.setFixedHeight(85)
        self.composer.submitted.connect(self.send_prompt)
        composition.addWidget(self.composer)
        controls = QHBoxLayout()
        self.voice_button = QPushButton("◉  Conversar por voz")
        self.voice_button.clicked.connect(self.controller._on_mic_clicked)
        controls.addWidget(self.voice_button)
        controls.addStretch()
        self.cancel_task_button = QPushButton("Interromper")
        self.cancel_task_button.setEnabled(False)
        self.cancel_task_button.clicked.connect(self.controller.cancel_task)
        controls.addWidget(self.cancel_task_button)
        self.send_button = QPushButton("Enviar  ↑")
        self.send_button.setObjectName("Primary")
        self.send_button.clicked.connect(self.send_prompt)
        controls.addWidget(self.send_button)
        composition.addLayout(controls)
        layout.addWidget(composer_frame)
        layout.addWidget(self._muted("Enter para enviar · Shift+Enter para nova linha · Ações sensíveis pedem confirmação."))
        self.pages.addWidget(page)

    def _dock(self, title: str, name: str, body: QWidget, area) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        body.setObjectName("DockBody")
        dock.setWidget(body)
        dock.setMinimumWidth(210)
        self.addDockWidget(area, dock)
        return dock

    def _build_sidebar(self) -> None:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 12, 18, 18)
        self._sidebar_layout = layout
        self._rail_spacer = None
        self.brand = QLabel("nyx ✧")
        self.brand.setObjectName("Brand")
        self.brand.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.brand)
        self.brand_sub = self._muted("Uma companhia. Muitas possibilidades.")
        self.brand_sub.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.brand_sub)
        self.new_button = QPushButton("+  Nova conversa")
        self.new_button.setObjectName("Primary")
        self.new_button.clicked.connect(self.new_chat)
        layout.addWidget(self.new_button)
        self.nav_buttons = []
        self._nav_labels = ("Conversa", "Agenda", "Personalizar", "Aprendizado", "Central")
        self._nav_glyphs = ("◌", "◷", "⚙", "✧", "▦")
        for index, (glyph, title) in enumerate(zip(self._nav_glyphs, self._nav_labels, strict=False)):
            button = QPushButton(f"{glyph}  {title}")
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, i=index: self.set_page(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.removeWidget(self.nav_buttons[4])
        layout.insertWidget(3, self.nav_buttons[4])
        layout.addSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar conversas  Ctrl+F")
        self.search.textChanged.connect(self._reload_chats)
        layout.addWidget(self.search)
        self.chat_list = QListWidget()
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.chat_list.setAccessibleName("Histórico de conversas")
        self.chat_list.itemClicked.connect(lambda item: self.activate_chat(item.data(Qt.ItemDataRole.UserRole)))
        self.chat_list.itemDoubleClicked.connect(self._rename_chat)
        layout.addWidget(self.chat_list, 1)
        self.remove_button = QPushButton("Excluir conversa selecionada")
        self.remove_button.setObjectName("Quiet")
        self.remove_button.clicked.connect(self._delete_chat)
        layout.addWidget(self.remove_button)
        self.sidebar = self._dock("Biblioteca", "library", body, Qt.DockWidgetArea.LeftDockWidgetArea)

    def _build_companion(self) -> None:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 4, 18, 18)
        self.companion = CompanionStage()
        layout.addWidget(self.companion)
        self.companion_state = QLabel("Pronta para ajudar")
        self.companion_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.companion_state)
        self.mode_button = QPushButton("Modo assistido")
        self.mode_button.clicked.connect(self.controller._toggle_mode_clicked)
        layout.addWidget(self.mode_button)
        floating = QPushButton("Mascote na área de trabalho")
        floating.clicked.connect(self._toggle_floating_companion)
        layout.addWidget(floating)
        creation = QPushButton("Abrir espaço de criação  ↗")
        creation.clicked.connect(self.controller._toggle_workspace)
        layout.addWidget(creation)
        layout.addStretch()
        self.ram_label = self._muted("Memória do sistema")
        layout.addWidget(self.ram_label)
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setTextVisible(False)
        layout.addWidget(self.ram_bar)
        self.queue_label = self._muted("Inferência local livre")
        layout.addWidget(self.queue_label)
        self.companion_dock = self._dock("Companhia e sistema", "companion", body, Qt.DockWidgetArea.RightDockWidgetArea)

    def _tab_section(self, tabs: QTabWidget, title: str) -> QVBoxLayout:
        section, layout = self._page()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(section)
        tabs.addTab(scroll, title)
        return layout

    def _build_evolution_page(self) -> None:
        page, outer = self._page()
        self.learning_tabs = QTabWidget()
        self.learning_section = QComboBox()
        self.learning_section.setAccessibleName("Área de aprendizado e recuperação")
        outer.addWidget(self.learning_section)
        outer.addWidget(self.learning_tabs)
        layout = self._tab_section(self.learning_tabs, "Estudos")
        layout.addWidget(self._muted("Conhecimento com fontes e propostas de habilidades. Simulações não executam ações nem comprovam resultados."))
        self.research_check = QCheckBox("Estudar documentação durante os intervalos")
        self.research_check.setChecked(self.settings.value("idle_research", True, type=bool))
        self.research_check.toggled.connect(self._research_enabled_changed)
        layout.addWidget(self.research_check)
        self.research_status = self._muted("Até 4 leituras por dia, uma a cada 15 minutos; começa após um minuto sem pedidos. Fontes: Python, Windows e Ollama.")
        layout.addWidget(self.research_status)
        self.study_topic = QLineEdit()
        self.study_topic.setPlaceholderText("Tema do estudo — por exemplo: gerenciar memória no Ollama")
        self.study_topic.setMaxLength(160)
        layout.addWidget(self.study_topic)
        self.study_source = QComboBox()
        from core.research import SOURCES
        for name, url in SOURCES.items():
            self.study_source.addItem(name, url)
        layout.addWidget(self.study_source)
        enqueue = QPushButton("Adicionar estudo à fila")
        enqueue.clicked.connect(self._enqueue_study)
        layout.addWidget(enqueue)
        self.study_jobs = QListWidget()
        self.study_jobs.setMaximumHeight(140)
        self.study_jobs.itemClicked.connect(self._show_study)
        layout.addWidget(self.study_jobs)
        cancel_study = QPushButton("Cancelar estudo selecionado")
        cancel_study.clicked.connect(self._cancel_study)
        layout.addWidget(cancel_study)
        self.study_preview = SafeMarkdown()
        self.study_preview.setObjectName("StudyPreview")
        self.study_preview.setPlaceholderText("Selecione um estudo para ver a fonte e o trecho coletado.")
        self.study_preview.setMinimumHeight(120)
        self.study_preview.setMaximumHeight(200)
        layout.addWidget(self.study_preview)
        layout = self._tab_section(self.learning_tabs, "Conhecimento")
        self.learning_list = QListWidget()
        self.learning_list.setWordWrap(True)
        self.learning_list.setMinimumHeight(180)
        layout.addWidget(self.learning_list, 1)
        refresh = QPushButton("Atualizar laboratório")
        refresh.clicked.connect(self._refresh_learning)
        layout.addWidget(refresh)
        research = QPushButton("Pesquisar e registrar um aprendizado")
        research.clicked.connect(lambda: self._prefill("Quero estudar um assunto. Pergunte qual tema; pesquise fontes reais, leia e registre notas com URLs usando evolution. Separe fatos de hipóteses."))
        layout.addWidget(research)
        layout = self._tab_section(self.learning_tabs, "Backups")
        self.backup_status = self._muted("Backup criptografado a cada 30 minutos enquanto a Nyx estiver aberta. GitHub usa as credenciais do Git deste computador.")
        layout.addWidget(self.backup_status)
        self.cloud_backup_check = QCheckBox("Copiar backup criptografado ao repositório privado autorizado")
        self.cloud_backup_check.setChecked(self.settings.value("cloud_backup", True, type=bool))
        self.cloud_backup_check.toggled.connect(lambda checked: self.settings.setValue("cloud_backup", checked))
        layout.addWidget(self.cloud_backup_check)
        backup = QPushButton("Criar backup criptografado agora")
        backup.clicked.connect(self._start_backup)
        layout.addWidget(backup)
        recovery = QPushButton("Guardar chave de recuperação…")
        recovery.clicked.connect(self._export_recovery_key)
        layout.addWidget(recovery)
        layout.addWidget(self._muted("Guarde a chave separada do backup: ela é necessária para recuperar os dados e permite ler seu conteúdo."))
        layout.addStretch()
        self._build_social_panels()
        self._build_task_history()
        self.learning_section.addItems([self.learning_tabs.tabText(i) for i in range(self.learning_tabs.count())])
        self.learning_section.currentIndexChanged.connect(self.learning_tabs.setCurrentIndex)
        self.learning_tabs.currentChanged.connect(self.learning_section.setCurrentIndex)
        self.learning_tabs.tabBar().hide()
        self.pages.addWidget(page)

    def _build_task_history(self):
        layout = self._tab_section(self.learning_tabs, "Tarefas")
        layout.addWidget(self._muted("Histórico local com pausa e retomada explícita. Resposta concluída não comprova que todo o objetivo foi alcançado. Efeitos incertos exigem revisão e um novo pedido."))
        self.task_budget_combo = QComboBox()
        self.task_budget_combo.addItem("Próximos pedidos: 6 ações / 3 minutos", "default")
        self.task_budget_combo.addItem("Próximos pedidos: 12 ações / 10 minutos", "extended")
        saved = str(self.settings.value("task_budget", "default"))
        self.task_budget_combo.setCurrentIndex(max(0, self.task_budget_combo.findData(saved)))
        self.task_budget_combo.currentIndexChanged.connect(self._set_task_budget)
        layout.addWidget(self.task_budget_combo)
        self._set_task_budget()
        self.task_history = QListWidget()
        self.task_history.itemClicked.connect(self._show_saved_task)
        layout.addWidget(self.task_history)
        self.task_preview = SafeMarkdown()
        self.task_preview.setObjectName("StudyPreview")
        layout.addWidget(self.task_preview)
        buttons = QHBoxLayout()
        for index, (label, callback) in enumerate((("Atualizar", self._refresh_tasks),
                                ("Pausar tarefa atual", self.controller.pause_task),
                                ("Retomar selecionada", self._continue_saved_task),
                                ("Excluir histórico selecionado", self._delete_saved_task))):
            if index == 2:
                layout.addLayout(buttons)
                buttons = QHBoxLayout()
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._refresh_tasks()

    def _set_task_budget(self):
        profile = self.task_budget_combo.currentData()
        self.settings.setValue("task_budget", profile)
        runner = getattr(self.controller.loop, "task_runner", None)
        if runner:
            runner.set_budget_profile(profile)

    def _task_journal(self):
        runner = getattr(self.controller.loop, "task_runner", None)
        return getattr(runner, "journal", None)

    def _refresh_tasks(self):
        if not hasattr(self, "task_history"):
            return
        self.task_history.clear()
        journal = self._task_journal()
        if journal is None:
            self.task_preview.setPlainText("Histórico persistente indisponível nesta sessão de diagnóstico.")
            return
        labels = {"PAUSED": "Pausada", "WAITING_REVIEW": "Revisão necessária",
                  "RESOURCE_PRESSURE": "Pausada por pressão de recursos",
                  "PLANNING_FINISHED": "Resposta concluída · objetivo não verificado",
                  "CANCELLED": "Cancelada", "FAILED": "Interrompida com pendência",
                  "ACT": "Executando", "PLAN": "Planejando", "OBSERVE": "Resultado observado",
                  "WAITING_USER": "Aguardando confirmação"}
        for task in journal.list():
            item = QListWidgetItem(f"{labels.get(task['state'], task['state'])} · {task['goal'][:100]}")
            item.setData(Qt.ItemDataRole.UserRole, task["id"])
            self.task_history.addItem(item)

    def _show_saved_task(self, item):
        journal = self._task_journal()
        if journal:
            task = journal.get(item.data(Qt.ItemDataRole.UserRole))
            lines = [task["goal"], "", f"Tarefa {task['id'][:12]}",
                     f"Etapas: {len(task['steps'])} de {task['max_actions']}",
                     f"Tempo utilizado: {task['spent']:.1f} de {task['timeout']} segundos", ""]
            if task.get("inflight") or task.get("uncertain"):
                lines += ["Resultado incerto. Confira o aplicativo antes de formular um novo pedido.", ""]
            for number, step in enumerate(task["steps"], 1):
                state = "confirmada" if step["verified"] else "sem confirmação"
                lines += [f"{number}. {step['tool']} · {state}", step["output"], ""]
                for subtask in step.get("subtasks", []):
                    dependencies = ", ".join(subtask["depends_on"]) or "nenhuma"
                    lines += [f"Subtarefa {subtask['id']} · {subtask['role']} · {subtask['state']}",
                              f"Dependências: {dependencies}", subtask["summary"], ""]
            self.task_preview.setPlainText("\n".join(lines))

    def _continue_saved_task(self):
        item = self.task_history.currentItem()
        if item:
            self.controller.continue_task(item.data(Qt.ItemDataRole.UserRole))

    def _delete_saved_task(self):
        item = self.task_history.currentItem()
        journal = self._task_journal()
        if not item or not journal:
            return
        if QMessageBox.question(self, "Excluir histórico", "Excluir este registro? Arquivos e efeitos das ações serão preservados.") != QMessageBox.StandardButton.Yes:
            return
        try:
            journal.delete(item.data(Qt.ItemDataRole.UserRole))
            self.task_preview.clear()
            self._refresh_tasks()
        except Exception as exc:
            self.toast.show_message(str(exc))

    def _build_social_panels(self):
        layout = self._tab_section(self.learning_tabs, "Observação e iniciativa")
        layout.addWidget(self._muted("O que a Nyx pode observar: apenas eventos autorizados abaixo. Sem captura contínua de tela, câmera ou microfone."))
        self.sensor_checks = {}
        permissions = self._context.permissions()
        for name, label in (("own_tasks", "Resultados das próprias tarefas"),
                            ("research", "Estudos autorizados concluídos"), ("resources", "Pressão de recursos"),
                            ("processes", "Encerramento dos processos escolhidos por PID")):
            check = QCheckBox(label)
            check.setChecked(permissions[name])
            check.toggled.connect(lambda enabled, sensor=name: self._set_sensor_permission(sensor, enabled))
            self.sensor_checks[name] = check
            layout.addWidget(check)
        watch = QPushButton("Escolher processo para observar…")
        watch.clicked.connect(self._watch_process)
        layout.addWidget(watch)
        self.process_watch_status = self._muted("Nenhum processo selecionado. As escolhas duram esta sessão; nenhum aplicativo será encerrado.")
        layout.addWidget(self.process_watch_status)
        layout.addWidget(self._muted("Janelas, pastas e navegador: sensores externos ainda não conectados; permanecem desligados."))
        self.initiative_history_list = QListWidget()
        self.initiative_history_list.setMaximumHeight(170)
        layout.addWidget(self.initiative_history_list)
        refresh = QPushButton("Ver motivo das iniciativas e acessos")
        refresh.clicked.connect(self._refresh_social)
        layout.addWidget(refresh)
        for label, response in (("Esta sugestão foi útil", "accepted"), ("Prefiro menos sugestões", "declined")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, value=response: self._initiative_feedback(value))
            layout.addWidget(button)
        self.access_history_view = SafeMarkdown()
        self.access_history_view.setObjectName("StudyPreview")
        self.access_history_view.setReadOnly(True)
        self.access_history_view.setPlaceholderText("Nenhuma coleta registrada. As permissões são verificadas antes de observar.")
        self.access_history_view.setMaximumHeight(140)
        layout.addWidget(self.access_history_view)
        clear = QPushButton("Apagar histórico de observações e iniciativas")
        clear.clicked.connect(self._clear_observations)
        layout.addWidget(clear)

        layout = self._tab_section(self.learning_tabs, "Memória e interesses")
        self.interests_enabled_check = QCheckBox("Guardar e usar interesses e preferências")
        self.interests_enabled_check.setChecked(self._interests.enabled)
        self.interests_enabled_check.toggled.connect(self._interests.set_enabled)
        layout.addWidget(self.interests_enabled_check)
        layout.addWidget(self._muted("Preferências inferidas são hipóteses. Interesses da Nyx são simulados. Estes registros não mudam permissões."))
        self.interest_list = QListWidget()
        self.interest_list.setMaximumHeight(240)
        self.interest_list.itemClicked.connect(self._select_interest)
        layout.addWidget(self.interest_list)
        self.interest_topic = QLineEdit()
        self.interest_topic.setMaxLength(160)
        self.interest_topic.setPlaceholderText("Tema, preferência ou projeto autorizado")
        layout.addWidget(self.interest_topic)
        self.interest_kind = QComboBox()
        for label, value in (("Preferência confirmada", "confirmed_preference"), ("Preferência inferida", "inferred_preference"),
                             ("Interesse simulado da Nyx", "simulated_interest"), ("Projeto", "project"), ("Fato informado", "fact")):
            self.interest_kind.addItem(label, value)
        layout.addWidget(self.interest_kind)
        save = QPushButton("Guardar ou corrigir registro selecionado")
        save.clicked.connect(self._save_interest)
        layout.addWidget(save)
        delete = QPushButton("Apagar registro selecionado")
        delete.clicked.connect(self._delete_interest)
        layout.addWidget(delete)
        self._refresh_social()

    def _refresh_social(self):
        self.initiative_history_list.clear()
        for row in self._initiative.history():
            item = QListWidgetItem(f"{row['message']}\n{row['reason']} · resposta: {row['response']}")
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.initiative_history_list.addItem(item)
        self.access_history_view.setPlainText("\n".join(f"{row['sensor']} · {row['outcome']}" for row in self._context.access_history()))
        self.interest_list.clear()
        for row in self._interests.records():
            label = self.interest_kind.itemText(self.interest_kind.findData(row["kind"]))
            item = QListWidgetItem(f"{row['topic']} · {label} · confiança {row['confidence']:.0%}")
            item.setToolTip(f"Origem: {row['origin']}\nFontes: {', '.join(row['sources'])}")
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.interest_list.addItem(item)

    def _set_sensor_permission(self, sensor, enabled):
        self._context.set_permission(sensor, enabled)
        if sensor == "processes" and not enabled:
            self._process_sensor.clear()
            self.process_watch_status.setText("Observação de processos desativada; seleção removida.")

    def _watch_process(self):
        if not self.sensor_checks["processes"].isChecked():
            self.process_watch_status.setText("Ative a permissão de observar processos antes de escolher um PID.")
            return
        pid, accepted = QInputDialog.getInt(self, "Observar processo autorizado", "PID do processo (Gerenciador de Tarefas):", 1, 1, 2_147_483_647)
        if accepted:
            try:
                entry = self._process_sensor.watch(pid)
                self.process_watch_status.setText(f"Observando encerramento de {entry.name} · PID {entry.pid}")
            except Exception as exc:
                self.process_watch_status.setText(f"Não foi possível observar: {exc}")

    def _initiative_feedback(self, response):
        item = self.initiative_history_list.currentItem()
        if item:
            self._initiative.respond(item.data(Qt.ItemDataRole.UserRole), response)
            self._refresh_social()

    def _clear_observations(self):
        self._context.clear()
        self._refresh_social()

    def _select_interest(self, item):
        row = item.data(Qt.ItemDataRole.UserRole)
        self.interest_topic.setText(row["topic"])
        self.interest_kind.setCurrentIndex(self.interest_kind.findData(row["kind"]))

    def _save_interest(self):
        if not self.interest_topic.text().strip() or not self._interests.enabled:
            return
        selected = self.interest_list.currentItem()
        previous = selected.data(Qt.ItemDataRole.UserRole)["id"] if selected else None
        kind = self.interest_kind.currentData()
        identifier = self._interests.remember(self.interest_topic.text(), kind=kind,
            origin="Informado na interface pelo usuário", confidence=.6 if kind == "inferred_preference" else 1)
        if previous and identifier and previous != identifier:
            self._interests.delete(previous)
        self.interest_topic.clear()
        self._refresh_social()

    def _delete_interest(self):
        item = self.interest_list.currentItem()
        if item:
            self._interests.delete(item.data(Qt.ItemDataRole.UserRole)["id"])
            self.interest_topic.clear()
            self._refresh_social()

    def _research_enabled_changed(self, enabled: bool) -> None:
        self.settings.setValue("idle_research", enabled)
        if not enabled:
            self._research_cancel.set()
        self.research_status.setText("Estudo durante intervalos ativado." if enabled else "Estudo automático pausado.")

    def _enqueue_study(self) -> None:
        queue = getattr(self.controller.loop.registry, "research_queue", None)
        if queue is None:
            return
        try:
            queue.enqueue(self.study_topic.text(), self.study_source.currentData())
            self.study_topic.clear()
            self.research_status.setText("Estudo salvo na fila. Será lido quando houver tempo e recursos disponíveis.")
            self._refresh_learning()
        except ValueError as exc:
            self.research_status.setText(str(exc))

    def _cancel_study(self) -> None:
        item = self.study_jobs.currentItem()
        queue = getattr(self.controller.loop.registry, "research_queue", None)
        if item and queue:
            queue.cancel(item.data(Qt.ItemDataRole.UserRole)["id"])
            self._refresh_learning()

    def _show_study(self, item) -> None:
        job = item.data(Qt.ItemDataRole.UserRole)
        text = f"{job['topic']}\nFonte: {job['url']}\n{job['detail']}"
        lab = getattr(self.controller.loop.registry, "evolution_lab", None)
        if lab and job["note_id"]:
            with lab.connect() as db:
                note = db.execute("SELECT content,source FROM knowledge WHERE id=?", (job["note_id"],)).fetchone()
                if note:
                    text += f"\n\nConteúdo externo não verificado — fonte final: {note['source']}\n\n{note['content']}"
        self.study_preview.setPlainText(text)

    def _research_tick(self) -> None:
        queue = getattr(self.controller.loop.registry, "research_queue", None)
        if (queue is None or not self.research_check.isChecked() or self._busy or self._backup_busy
                or self._research_busy or self.focus_button.isChecked()
                or self.controller.current_emotion in {"listening", "think", "talk"}
                or time.monotonic() - self._last_interaction < 60):
            return
        try:
            import psutil
            from core.resource_governor import RESOURCE_GOVERNOR
            from core.runtime_budget import INFERENCE_GATE, ResourceSnapshot, WorkPriority
            memory = psutil.virtual_memory()
            queue_state = INFERENCE_GATE.telemetry()
            decision = RESOURCE_GOVERNOR.evaluate(
                ResourceSnapshot(memory.available, None, None, psutil.cpu_percent(), memory.total),
                WorkPriority.BACKGROUND, queued=queue_state["active"] + queue_state["waiting"],
            )
            if not decision.allowed:
                self.research_status.setText(decision.reason)
                return
        except ImportError:
            return
        queue.seed_curiosity()
        self._research_busy = True
        self._research_cancel.clear()

        def worker():
            try:
                result = queue.run_one(cancelled=self._research_cancel.is_set)
            except Exception as exc:
                result = {"state": "failed", "topic": "Pesquisa", "error": str(exc)}
            if not self._closing:
                self.research_finished.emit(result)

        threading.Thread(target=worker, name="nyx-idle-study", daemon=True).start()

    def _research_done(self, result) -> None:
        self._research_busy = False
        if result:
            labels = {"completed": "Trecho coletado", "failed": "Estudo falhou", "cancelled": "Estudo cancelado", "deferred": "Estudo adiado"}
            message = f"{labels.get(result['state'], result['state'])}: {result['topic']}"
            self.research_status.setText(message)
            self._add_activity(message)
            if result["state"] == "completed":
                self._context.emit("research", "research_found", result.get("note_id", result["topic"]),
                                   result["topic"], source=result.get("source", ""))
                if self._context.permissions()["research"]:
                    self._interests.remember(result["topic"], kind="simulated_interest", origin="Estudo autorizado",
                                             confidence=.6, relevance=.6, source=result.get("source", ""),
                                             experience="Referência coletada; conteúdo não verificado")
        self._refresh_learning()

    def _refresh_learning(self) -> None:
        self.learning_list.clear()
        lab = getattr(self.controller.loop.registry, "evolution_lab", None)
        if lab is None:
            self.learning_list.addItem("Laboratório não disponível nesta sessão de diagnóstico.")
            return
        data = lab.overview()
        queue = getattr(self.controller.loop.registry, "research_queue", None)
        if queue:
            self.study_jobs.clear()
            states = {"queued": "Na fila", "running": "Lendo fonte", "completed": "Coletado", "failed": "Falhou", "cancelled": "Cancelado"}
            for job in queue.list_jobs():
                item = QListWidgetItem(f"{states.get(job['state'], job['state'])} · {job['topic']}")
                item.setData(Qt.ItemDataRole.UserRole, job)
                self.study_jobs.addItem(item)
        self.learning_list.addItem(f"{data['knowledge_count']} notas de pesquisa armazenadas com fontes · conteúdo externo não verificado")
        for proposal in data["proposals"]:
            self.learning_list.addItem(f"{proposal['name']} · {proposal['status']}\n{proposal['id']}")

    def _start_backup(self) -> None:
        if self._backup_busy or self._busy:
            self.backup_status.setText("Backup adiado: uma tarefa está em andamento.")
            return
        from core.backup import BackupVault

        self._backup_busy = True
        cloud_enabled = self.cloud_backup_check.isChecked()
        self.backup_status.setText("Criando backup criptografado…")

        def worker():
            try:
                path = BackupVault(user_data_dir()).create()
                message = f"Backup local criado: {path.name}."
                if cloud_enabled:
                    from core.cloud_backup import CloudBackup
                    try:
                        sha = CloudBackup(user_data_dir()).upload(path)
                        message += f" Cópia criptografada confirmada no GitHub ({sha[:8]})."
                    except Exception as exc:
                        message += f" Cópia na nuvem pendente: {exc}"
            except Exception as exc:
                message = f"Falha no backup: {exc}"
            if not self._closing:
                self.backup_finished.emit(message)

        threading.Thread(target=worker, name="nyx-backup", daemon=True).start()

    def _backup_done(self, message: str) -> None:
        self._backup_busy = False
        self.backup_status.setText(message)
        self._add_activity(message)

    def _export_recovery_key(self) -> None:
        from core.backup import BackupVault

        vault = BackupVault(user_data_dir())
        if not vault.key_path.is_file():
            self.backup_status.setText("Crie o primeiro backup para gerar sua chave de recuperação.")
            return
        destination, _ = QFileDialog.getSaveFileName(self, "Guardar chave separada do backup", "nyx-recovery.key", "Chave (*.key)")
        if destination:
            try:
                shutil.copyfile(vault.key_path, destination)
                self.backup_status.setText("Chave exportada. Guarde-a em local privado e separado do backup.")
            except OSError as exc:
                self.backup_status.setText(f"Falha ao exportar chave: {exc}")

    def _build_activity(self) -> None:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.addWidget(self._muted("Acompanhe o que foi solicitado, confirmado e executado nesta sessão."))
        self.activity = QListWidget()
        self.activity.setWordWrap(True)
        layout.addWidget(self.activity)
        self.activity_dock = self._dock("Atividade real", "activity", body, Qt.DockWidgetArea.RightDockWidgetArea)
        self.splitDockWidget(self.companion_dock, self.activity_dock, Qt.Orientation.Vertical)
        self.resizeDocks([self.sidebar, self.companion_dock], [245, 270], Qt.Orientation.Horizontal)

    def _build_agenda_page(self) -> None:
        page, layout = self._page()
        layout.addWidget(self._muted("Lembretes ficam salvos neste computador e são avisados enquanto a Nyx estiver aberta."))
        self.reminder_text = QLineEdit()
        self.reminder_text.setPlaceholderText("Do que você quer se lembrar?")
        self.reminder_text.setMaxLength(500)
        layout.addWidget(self.reminder_text)
        row = QHBoxLayout()
        self.reminder_date = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.reminder_date.setCalendarPopup(True)
        self.reminder_date.setDisplayFormat("dd/MM/yyyy HH:mm")
        row.addWidget(self.reminder_date)
        add = QPushButton("Criar lembrete")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_reminder)
        row.addWidget(add)
        layout.addLayout(row)
        self.agenda_empty = self._muted("Sua agenda está livre. Crie um lembrete acima para começar.")
        layout.addWidget(self.agenda_empty)
        self.reminders = QListWidget()
        self.reminders.setWordWrap(True)
        layout.addWidget(self.reminders, 1)
        self.cancel_reminder_button = QPushButton("Cancelar lembrete selecionado")
        self.cancel_reminder_button.setEnabled(False)
        self.cancel_reminder_button.clicked.connect(self._cancel_reminder)
        self.reminders.itemSelectionChanged.connect(
            lambda: self.cancel_reminder_button.setEnabled(bool(self.reminders.selectedItems())))
        layout.addWidget(self.cancel_reminder_button)
        self.agenda_feedback = self._muted("")
        layout.addWidget(self.agenda_feedback)
        self.pages.addWidget(page)

    def _build_settings_page(self) -> None:
        page, outer = self._page()
        self.settings_tabs = QTabWidget()
        outer.addWidget(self.settings_tabs)
        layout = self._tab_section(self.settings_tabs, "Aparência")
        layout.addWidget(self._muted("Faça este espaço funcionar do seu jeito. As preferências e a posição dos painéis são salvas automaticamente."))
        form = QFormLayout()
        form.setSpacing(18)
        self.theme_combo = QComboBox()
        for caption, value in (("Noite", "midnight"), ("Aurora", "aurora"), ("Dia", "daylight")):
            self.theme_combo.addItem(caption, value)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.settings.value("theme", "midnight"))))
        form.addRow("Aparência", self.theme_combo)
        self.accent_combo = QComboBox()
        for caption, value in (("Violeta", "violet"), ("Ciano", "cyan"), ("Menta", "mint"), ("Âmbar", "amber")):
            self.accent_combo.addItem(caption, value)
        self.accent_combo.setCurrentIndex(max(0, self.accent_combo.findData(self.settings.value("accent", "violet"))))
        form.addRow("Cor de destaque", self.accent_combo)
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(12, 18)
        self.font_slider.setValue(self.settings.value("font_size", 14, type=int))
        form.addRow("Tamanho do texto", self.font_slider)
        self.motion_check = QCheckBox("Animações suaves e companhia em movimento")
        self.motion_check.setChecked(self.settings.value("motion", True, type=bool))
        form.addRow(self.motion_check)
        self.speech_check = QCheckBox("Ler as respostas em voz alta")
        self.speech_check.setChecked(self.settings.value("speech", True, type=bool))
        layout.addLayout(form)
        layout.addStretch()
        layout = self._tab_section(self.settings_tabs, "Rotina")
        layout.addWidget(self._muted("Defina quando a Nyx pode iniciar uma conversa e com que frequência."))
        form = QFormLayout()
        form.setSpacing(18)
        self.initiative_check = QCheckBox("Nyx pode iniciar uma conversa nos intervalos")
        self.initiative_check.setChecked(self.settings.value("conversation_initiative", True, type=bool))
        self.initiative_check.setToolTip("Somente eventos relevantes, sem convites genéricos. Limites persistem ao reiniciar. Foco silencia os convites.")
        self.initiative_check.toggled.connect(lambda value: self.settings.setValue("conversation_initiative", value))
        form.addRow(self.initiative_check)
        self.initiative_level = QComboBox()
        for label, value in (("Desligada", "off"), ("Discreta", "discreet"), ("Normal", "normal"), ("Conversadora", "chatty")):
            self.initiative_level.addItem(label, value)
        self.initiative_level.setCurrentIndex(max(0, self.initiative_level.findData(self.settings.value("initiative_level", "discreet"))))
        self.initiative_level.currentIndexChanged.connect(lambda: self.settings.setValue("initiative_level", self.initiative_level.currentData()))
        form.addRow("Iniciativa contextual", self.initiative_level)
        self.initiative_limits = {}
        for key, label, low, high, default in (
            ("daily_limit", "Máximo de sugestões por dia", 0, 20, 3),
            ("interval_minutes", "Intervalo mínimo (minutos)", 5, 1440, 30),
            ("start_hour", "Início permitido (hora)", 0, 23, 9),
            ("end_hour", "Fim permitido (hora)", 0, 23, 21),
        ):
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(self.settings.value("initiative_" + key, default, type=int))
            spin.valueChanged.connect(lambda value, name=key: self.settings.setValue("initiative_" + name, value))
            self.initiative_limits[key] = spin
            form.addRow(label, spin)
        layout.addLayout(form)
        layout.addStretch()
        layout = self._tab_section(self.settings_tabs, "Sistema")
        layout.addWidget(self._muted("Reserve memória para seus aplicativos e ajuste o navegador da Nyx."))
        form = QFormLayout()
        form.setSpacing(18)
        self.ram_reserve_spin = QSpinBox()
        self.ram_reserve_spin.setRange(1024, 8192)
        self.ram_reserve_spin.setSingleStep(256)
        self.ram_reserve_spin.setValue(self.settings.value("ram_reserve_mib", 1024, type=int))
        self.ram_reserve_spin.setSuffix(" MiB")
        self.ram_reserve_spin.setToolTip("Memória livre mínima do sistema antes de iniciar novas inferências. Não é um limite de consumo por processo.")
        form.addRow("Reserva de RAM", self.ram_reserve_spin)
        self.vram_reserve_spin = QSpinBox()
        self.vram_reserve_spin.setRange(768, 6144)
        self.vram_reserve_spin.setSingleStep(256)
        self.vram_reserve_spin.setValue(self.settings.value("vram_reserve_mib", 768, type=int))
        self.vram_reserve_spin.setSuffix(" MiB")
        form.addRow("Reserva de VRAM", self.vram_reserve_spin)
        self.ram_reserve_spin.valueChanged.connect(self._update_resource_policy)
        self.vram_reserve_spin.valueChanged.connect(self._update_resource_policy)
        self._update_resource_policy()
        self.browser_visible_check = QCheckBox("Mostrar o navegador controlado pela Nyx")
        self.browser_visible_check.setChecked(self.settings.value("browser_visible", True, type=bool))
        form.addRow(self.browser_visible_check)
        self.browser_persist_check = QCheckBox("Manter logins no perfil isolado da Nyx")
        self.browser_persist_check.setChecked(self.settings.value("browser_persistent", False, type=bool))
        self.browser_persist_check.setToolTip("Ao ativar, autoriza guardar a sessão deste navegador localmente. Entre nas contas você mesmo. Nenhum dado do navegador pessoal é copiado. Desativar deixa de usar o perfil, sem apagar seus dados.")
        form.addRow(self.browser_persist_check)
        self.browser_preferences_note = QLabel("Mudanças valem na próxima abertura. Login é feito por você na janela do navegador.")
        self.browser_preferences_note.setWordWrap(True)
        form.addRow(self.browser_preferences_note)
        self.browser_visible_check.toggled.connect(self._update_browser_preferences)
        self.browser_persist_check.toggled.connect(self._update_browser_preferences)
        self._update_browser_preferences()
        layout.addLayout(form)
        layout.addStretch()
        layout = self._tab_section(self.settings_tabs, "Voz")
        layout.addWidget(self._muted("Escolha a voz local, ajuste a reprodução e ouça uma amostra."))
        form = QFormLayout()
        form.setSpacing(18)
        form.addRow(self.speech_check)
        from audio.tts import DEFAULT_SPEED, DEFAULT_VOLUME, KOKORO_VOICE, PT_BR_VOICES

        self.voice_combo = QComboBox()
        for voice_id, caption in PT_BR_VOICES:
            self.voice_combo.addItem(caption, voice_id)
        self.voice_combo.setCurrentIndex(
            max(0, self.voice_combo.findData(self.settings.value("voice", KOKORO_VOICE)))
        )
        self.voice_combo.setToolTip("Vozes pt-BR do Kokoro executadas neste computador")
        form.addRow("Voz da Nyx", self.voice_combo)
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(70, 150)
        self.speed_slider.setSingleStep(5)
        self.speed_slider.setPageStep(10)
        self.speed_slider.setValue(self.settings.value("voice_speed", round(DEFAULT_SPEED * 100), type=int))
        self.speed_slider.setToolTip("70% mais lenta · 100% natural · 150% mais rápida")
        speed_row, self.speed_readout = self._slider_with_readout(self.speed_slider)
        form.addRow("Velocidade da fala", speed_row)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setSingleStep(5)
        self.volume_slider.setPageStep(10)
        self.volume_slider.setValue(self.settings.value("voice_volume", int(DEFAULT_VOLUME * 100), type=int))
        self.volume_slider.setToolTip("0 silencia a voz · 100 reproduz no volume máximo")
        volume_row, self.volume_readout = self._slider_with_readout(self.volume_slider)
        form.addRow("Volume da voz", volume_row)
        preview = QPushButton("Ouvir uma amostra")
        preview.clicked.connect(self._preview_voice)
        form.addRow(preview)
        self.voice_feedback = self._muted("As preferências de voz valem para a conversa e para o pet.")
        layout.addWidget(self.voice_feedback)
        layout.addLayout(form)
        layout.addStretch()
        layout = self._tab_section(self.settings_tabs, "Modelo local")
        from core.ollama_service import load_runtime_config

        runtime = load_runtime_config()
        runtime_form = QFormLayout()
        runtime_form.setSpacing(12)
        self.ollama_path = QLineEdit(runtime.get("ollama_executable", ""))
        self.ollama_path.setPlaceholderText("Detectar instalação automaticamente")
        binary_row = QHBoxLayout()
        binary_row.addWidget(self.ollama_path)
        binary_button = QPushButton("Escolher…")
        binary_button.clicked.connect(self._choose_ollama)
        binary_row.addWidget(binary_button)
        runtime_form.addRow("Ollama", binary_row)
        self.models_path = QLineEdit(runtime.get("models_directory", ""))
        self.models_path.setPlaceholderText("Pasta padrão do Ollama")
        models_row = QHBoxLayout()
        models_row.addWidget(self.models_path)
        models_button = QPushButton("Escolher…")
        models_button.clicked.connect(self._choose_models)
        models_row.addWidget(models_button)
        runtime_form.addRow("Modelos locais", models_row)
        self.preferred_model = QLineEdit(runtime.get("preferred_model", ""))
        self.preferred_model.setMaxLength(160)
        self.preferred_model.setPlaceholderText("Automático (se vazio)")
        self.preferred_model.setToolTip("Nome exato no Ollama. Se não houver memória, a Nyx aguarda em vez de trocar por um modelo menor.")
        runtime_form.addRow("Modelo principal", self.preferred_model)
        layout.addLayout(runtime_form)
        save_runtime = QPushButton("Salvar configuração do modelo")
        save_runtime.clicked.connect(self._save_runtime)
        layout.addWidget(save_runtime)
        self.runtime_feedback = self._muted("Reinicie a Nyx após alterar o modelo principal. Se faltar memória, ela aguardará recursos sem trocar de modelo. Os caminhos são usados ao iniciar o Ollama.")
        layout.addWidget(self.runtime_feedback)
        reset = QPushButton("Restaurar organização dos painéis")
        reset.clicked.connect(self._reset_layout)
        layout.addWidget(reset)
        layout.addStretch()
        layout.addWidget(self._muted("Painéis podem ser arrastados, ocultados e destacados. Use o menu Painéis para reabri-los.\nA aparência muda a interface; as capacidades continuam dependendo do modelo local e das ferramentas instaladas."))
        self.pages.addWidget(page)
        self.theme_combo.currentIndexChanged.connect(self._apply_preferences)
        self.accent_combo.currentIndexChanged.connect(self._apply_preferences)
        self.font_slider.valueChanged.connect(self._apply_preferences)
        self.motion_check.toggled.connect(self._apply_preferences)
        self.speech_check.toggled.connect(self._apply_preferences)
        self.voice_combo.currentIndexChanged.connect(self._apply_preferences)
        self.speed_slider.valueChanged.connect(self._apply_preferences)
        self.volume_slider.valueChanged.connect(self._apply_preferences)

    def _update_browser_preferences(self) -> None:
        visible = self.browser_visible_check.isChecked()
        persistent = self.browser_persist_check.isChecked()
        self.settings.setValue("browser_visible", visible)
        self.settings.setValue("browser_persistent", persistent)
        browser = getattr(self.controller.loop.registry, "browser_session", None)
        if browser is not None:
            browser.headless = not visible
            browser.persistent_profile = self.store.database.parent / "browser_profiles" / "default" if persistent else None

    def _update_resource_policy(self, *_args) -> None:
        from core.resource_governor import RESOURCE_GOVERNOR, ResourcePolicy
        from core.runtime_budget import MIB, GIB
        ram, vram = self.ram_reserve_spin.value(), self.vram_reserve_spin.value()
        RESOURCE_GOVERNOR.configure(ResourcePolicy(
            ram_reserve_bytes=ram * MIB, vram_reserve_bytes=vram * MIB,
            background_ram_bytes=max(3 * GIB, ram * MIB),
        ))
        self.settings.setValue("ram_reserve_mib", ram)
        self.settings.setValue("vram_reserve_mib", vram)

    def _preview_voice(self) -> None:
        tts = getattr(self.controller, "tts", None)
        if not self.speech_check.isChecked():
            self.voice_feedback.setText("Ative “Ler as respostas em voz alta” para ouvir a amostra.")
            return
        if tts is None or not hasattr(tts, "speak"):
            self.voice_feedback.setText("A saída de voz não está disponível nesta sessão.")
            return
        tts.speak("Oi! Eu sou a Nyx. É assim que eu vou falar com você.")
        self.voice_feedback.setText("Tocando uma amostra com a voz selecionada…")

    def _choose_ollama(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecione o Ollama instalado", self.ollama_path.text(), "Ollama (ollama.exe ollama)")
        if path:
            self.ollama_path.setText(path)

    def _choose_models(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pasta dos modelos Ollama", self.models_path.text())
        if path:
            self.models_path.setText(path)

    def _save_runtime(self) -> None:
        from core.ollama_service import save_runtime_config

        try:
            save_runtime_config(self.ollama_path.text().strip(), self.models_path.text().strip(), self.preferred_model.text().strip())
            self.runtime_feedback.setText("Configuração salva. Reinicie a Nyx para aplicar o modelo principal. Os caminhos são usados ao iniciar o serviço Ollama.")
            self.notify("Configuração do modelo salva")
        except (OSError, ValueError) as exc:
            self.runtime_feedback.setText(str(exc))

    def _build_menu(self) -> None:
        menu = QMenu(self)
        for dock in (self.sidebar, self.companion_dock, self.activity_dock):
            menu.addAction(dock.toggleViewAction())
        menu.addSeparator()
        update = menu.addAction("Verificar atualizações")
        from core.updater import updater_supported

        update.setEnabled(updater_supported())
        update.triggered.connect(self.controller._check_for_updates)
        self.panel_button.setMenu(menu)

    def _connect_controller(self) -> None:
        self.controller.task_progress.connect(self._on_task_progress)
        self.controller.message_received.connect(self._on_message)
        self.controller.processing_changed.connect(self._on_processing)
        self.controller.emotion_changed.connect(self._on_emotion)
        self.controller.action_observed.connect(self._on_action)

    def _apply_preferences(self, *_args) -> None:
        theme = self.theme_combo.currentData()
        accent = self.accent_combo.currentData()
        self.setStyleSheet(desktop_stylesheet(theme, accent, self.font_slider.value()))
        from ui.workspace_window import WorkspaceWindow
        if WorkspaceWindow._instance is not None:
            WorkspaceWindow._instance.setStyleSheet(self.styleSheet())
        self.companion.accent = QColor(ACCENTS[accent])
        self.companion.set_motion(self.motion_check.isChecked())
        self.hero_companion.accent = QColor(ACCENTS[accent])
        self.hero_companion.set_motion(self.motion_check.isChecked())
        self.controller.setStyleSheet(desktop_stylesheet(theme, accent, self.font_slider.value()))
        self.controller.set_motion(self.motion_check.isChecked())
        if not self.motion_check.isChecked():
            self._stop_transition()
        options = QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AllowNestedDocks
        if self.motion_check.isChecked():
            options |= QMainWindow.DockOption.AnimatedDocks
        self.setDockOptions(options)
        self.controller.tts.enabled = self.speech_check.isChecked()
        if not self.speech_check.isChecked():
            self.controller.tts.stop_current()
        voice = self.voice_combo.currentData()
        configure = getattr(self.controller.tts, "configure", None)
        if callable(configure):
            configure(
                voice=voice,
                speed=self.speed_slider.value() / 100.0,
                volume=self.volume_slider.value() / 100.0,
            )
        for key, value in (("theme", theme), ("accent", accent), ("font_size", self.font_slider.value()), ("motion", self.motion_check.isChecked()), ("speech", self.speech_check.isChecked()), ("voice", voice), ("voice_speed", self.speed_slider.value()), ("voice_volume", self.volume_slider.value())):
            self.settings.setValue(key, value)

    def open_palette(self) -> None:
        """Ctrl+K: searchable actions followed by recent conversations."""
        commands = [
            ("Abrir Central da Nyx", "Ctrl+1", lambda: self.set_page(4)),
            ("Abrir Estúdio", "", lambda: self._open_center_route("studio")),
            ("Memória e interesses", "", lambda: self._open_center_route("memory")),
            ("Sensores e privacidade", "", lambda: self._open_center_route("privacy")),
            ("Nova conversa", "Ctrl+N", self.new_chat),
            ("Ir para Conversa", "", lambda: self.set_page(0)),
            ("Ir para Agenda", "", lambda: self.set_page(1)),
            ("Ir para Personalizar", "", lambda: self.set_page(2)),
            ("Ir para Aprendizado", "", lambda: self.set_page(3)),
            ("Buscar conversas", "Ctrl+F", lambda: self.search.setFocus()),
            ("Conversar por voz", "", self.controller._on_mic_clicked),
            ("Modo foco", "", lambda: self.focus_button.setChecked(not self.focus_button.isChecked())),
            ("Recolher barra lateral", "Ctrl+B", lambda: self._set_rail(not self._rail)),
            ("Verificar atualizações", "", self.controller._check_for_updates),
        ]
        for chat in self.store.list_chats()[:8]:
            title = str(chat.get("title") or "Sem título")
            commands.append(
                (f"Abrir conversa: {title}", "histórico", lambda cid=chat["id"]: self.activate_chat(cid))
            )
        self.palette.set_commands(commands)
        self.palette.open_with()
        self.palette.focus_in_parent()

    def notify(self, text: str) -> None:
        """Small, self-dismissing feedback instead of a modal dialog."""
        self.toast.show_message(text)

    def _set_rail(self, enabled: bool) -> None:
        """Collapse the library into an icon rail to give the conversation room."""
        self._rail = bool(enabled)
        self.brand.setText("✧" if self._rail else "nyx ✧")
        self.brand_sub.setVisible(not self._rail)
        self.new_button.setText("+" if self._rail else "+  Nova conversa")
        self.search.setVisible(not self._rail)
        self.chat_list.setVisible(not self._rail)
        self.remove_button.setVisible(not self._rail)
        for button, glyph, label in zip(self.nav_buttons, self._nav_glyphs, self._nav_labels, strict=False):
            button.setText(glyph if self._rail else f"{glyph}  {label}")
            button.setToolTip(label if self._rail else "")
        if self._rail:
            if self._rail_spacer is None:
                self._rail_spacer = QSpacerItem(
                    0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
                )
                self._sidebar_layout.addItem(self._rail_spacer)
        else:
            if self._rail_spacer is not None:
                self._sidebar_layout.removeItem(self._rail_spacer)
                self._rail_spacer = None
        body = self.sidebar.widget()
        if body is not None and body.layout() is not None:
            body.layout().invalidate()
            body.layout().activate()
        target = 78 if self._rail else 245
        if self.motion_check.isChecked() and self.isVisible():
            self._animate_rail(target)
        else:
            self._apply_rail_width(target, final=True)
        self.settings.setValue("sidebar_rail", self._rail)

    def _animate_rail(self, target: int) -> None:
        """Animate the library width instead of snapping between states."""
        self._stop_rail_animation()
        self._rail_target = target
        self._rail_started_at = time.monotonic()
        self._rail_start_width = self.sidebar.width()
        self._rail_timer = QTimer(self)
        self._rail_timer.setInterval(16)
        self._rail_timer.timeout.connect(self._rail_tick)
        self._rail_timer.start()

    def _stop_rail_animation(self) -> None:
        timer = getattr(self, "_rail_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
            self._rail_timer = None
        if self._rail_anim is not None:
            self._rail_anim.stop()
            self._rail_anim.deleteLater()
            self._rail_anim = None

    def _rail_tick(self) -> None:
        elapsed = time.monotonic() - self._rail_started_at
        progress = min(1.0, elapsed / 0.22)
        eased = 1.0 - (1.0 - progress) ** 3
        width = int(self._rail_start_width + (self._rail_target - self._rail_start_width) * eased)
        self._apply_rail_width(width, final=progress >= 1.0)
        if progress >= 1.0:
            self._stop_rail_animation()

    def _apply_rail_width(self, width: int, final: bool) -> None:
        width = max(60, width)
        self.sidebar.setMinimumWidth(width)
        self.sidebar.setMaximumWidth(width)
        self.resizeDocks([self.sidebar], [width], Qt.Orientation.Horizontal)
        if final and not self._rail:
            self.sidebar.setMinimumWidth(0)
            self.sidebar.setMaximumWidth(16777215)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "companion_dock"):
            self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """Drop the companion gallery on narrow windows and bring it back later."""
        narrow = self.width() < 1120
        if narrow and self.companion_dock.isVisible() and not self.companion_dock.isFloating():
            self.companion_dock.hide()
            self._companion_auto_hidden = True
        elif not narrow and self._companion_auto_hidden:
            self.companion_dock.show()
            self._companion_auto_hidden = False
        compact = self.width() < 1180
        self.model_badge.setVisible(not compact)
        if hasattr(self, "activity_dock") and not self.focus_button.isChecked():
            if compact and self.activity_dock.isVisible() and not self.activity_dock.isFloating():
                self.activity_dock.hide()
                self._activity_auto_hidden = True
            elif not compact and self._activity_auto_hidden:
                self.activity_dock.show()
                self._activity_auto_hidden = False

    def _restore_layout(self) -> None:
        geometry = self.settings.value("geometry")
        state = self.settings.value("dock_state")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

    def _reset_layout(self) -> None:
        for dock in (self.sidebar, self.companion_dock, self.activity_dock):
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.companion_dock)
        self.splitDockWidget(self.companion_dock, self.activity_dock, Qt.Orientation.Vertical)
        self.resizeDocks([self.sidebar, self.companion_dock], [245, 270], Qt.Orientation.Horizontal)
        self.notify("Painéis restaurados")

    def set_page(self, index: int) -> None:
        if not 0 <= index < self.pages.count():
            return
        self.pages.setCurrentIndex(index)
        self.page_title.setText(("Conversa", "Sua agenda", "Do seu jeito", "Aprendizado e recuperação", "Central da Nyx")[index])
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if index == 1:
            self._refresh_reminders()
        elif index == 3:
            self._refresh_learning()
        elif index == 4:
            self._refresh_center_tasks()
            self._refresh_status()
        if self.motion_check.isChecked():
            self._stop_transition()
            page = self.pages.currentWidget()
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(170)
            animation.setStartValue(0.4)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(self._stop_transition)
            self._animation = animation
            self._animated_page = page
            animation.start()

    def _stop_transition(self) -> None:
        if self._animation:
            animation = self._animation
            self._animation = None
            animation.stop()
            animation.deleteLater()
        if self._animated_page:
            self._animated_page.setGraphicsEffect(None)
            self._animated_page = None

    def _prefill(self, text: str) -> None:
        self.set_page(0)
        self.composer.setPlainText(text)
        self.composer.setFocus()

    def send_prompt(self) -> None:
        text = self.composer.toPlainText().strip()
        if not text or self._busy:
            return
        self.composer.clear()
        self.controller.tts.stop_current()
        self.controller.process_prompt(text)

    def _initiative_tick(self) -> None:
        from core.initiative import InitiativePreferences
        from core.resource_governor import RESOURCE_GOVERNOR
        pressure = RESOURCE_GOVERNOR.telemetry()["mode"] == "pressure"
        self._process_sensor.poll(under_load=pressure or self._busy)
        if pressure and self._pressure_event is None:
            self._pressure_event = self._context.emit("resources", "resource_pressure", "resource-admission", "memória", ttl=1800)
        elif not pressure and self._pressure_event:
            self._context.resolve(self._pressure_event)
            self._pressure_event = None
        self._initiative.preferences = InitiativePreferences(
            level=self.initiative_level.currentData(),
            daily_limit=self.initiative_limits["daily_limit"].value(),
            interval_seconds=self.initiative_limits["interval_minutes"].value() * 60,
            start_hour=self.initiative_limits["start_hour"].value(),
            end_hour=self.initiative_limits["end_hour"].value(),
        )
        message = self._initiative.poll(
            enabled=self.initiative_check.isChecked() and not self._closing,
            busy=(self._busy or self._research_busy or self._backup_busy
                  or bool(self.composer.toPlainText().strip())
                  or self.controller.current_emotion in {"listening", "think", "talk"}),
            focused=self.focus_button.isChecked(),
            resource_pressure=pressure,
        )
        if message:
            self.controller.say(message, emotion="surprised")
            self._add_activity(self._initiative.last_explanation)

    def _on_message(self, role: str, text: str) -> None:
        if role == "user":
            self._initiative.activity()
            reply = text.strip().lower().rstrip(".!?")
            if self._initiative.last_offer_id and reply in {"agora não", "não", "estou ocupado", "sim", "pode falar"}:
                response = "accepted" if reply in {"sim", "pode falar"} else "declined"
                self._initiative.respond(self._initiative.last_offer_id, response)
                self._initiative.last_offer_id = None
        self.store.append(self.chat_id, role, text)
        self._add_card(role, text)
        self._reload_chats()
        if role == "error":
            self._add_activity("Falha no pedido: " + text[:150])

    def _add_card(self, role: str, text: str) -> None:
        self.hero.hide()
        card = MessageCard(role, text, self.feed)
        row: QWidget = card
        if role == "user":
            row = QWidget(self.feed)
            row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addStretch(1)
            row_layout.addWidget(card, 3)
        self.feed_layout.insertWidget(self.feed_layout.count() - 1, row)
        self._cards.append(row)
        while len(self._cards) > 100:
            old = self._cards.pop(0)
            self.feed_layout.removeWidget(old)
            old.deleteLater()
        QTimer.singleShot(30, self._scroll_to_latest)

    def _scroll_to_latest(self) -> None:
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _show_typing(self) -> None:
        """Animated placeholder so the conversation never looks frozen."""
        if self._typing_row is not None:
            return
        self.hero.hide()
        row = QWidget(self.feed)
        row.setObjectName("TypingRow")
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        bubble = QFrame(row)
        bubble.setObjectName("TypingBubble")
        bubble.setMaximumWidth(280)
        inner = QHBoxLayout(bubble)
        inner.setContentsMargins(16, 10, 16, 10)
        inner.setSpacing(10)
        text = QLabel("Nyx está pensando")
        text.setObjectName("TypingText")
        dots = QLabel("●  ●  ●")
        dots.setObjectName("TypingDots")
        inner.addWidget(text)
        inner.addWidget(dots)
        line.addWidget(bubble)
        line.addStretch(1)

        effect = QGraphicsOpacityEffect(row)
        effect.setOpacity(0.85)
        row.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(1400)
        animation.setLoopCount(-1)
        animation.setKeyValueAt(0.0, 0.45)
        animation.setKeyValueAt(0.5, 1.0)
        animation.setKeyValueAt(1.0, 0.45)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        animation.start()

        self.feed_layout.insertWidget(self.feed_layout.count() - 1, row)
        self._typing_row = row
        self._typing_anim = animation
        QTimer.singleShot(30, self._scroll_to_latest)

    def _hide_typing(self) -> None:
        if self._typing_row is None:
            return
        if self._typing_anim is not None:
            self._typing_anim.stop()
            self._typing_anim.deleteLater()
            self._typing_anim = None
        self.feed_layout.removeWidget(self._typing_row)
        self._typing_row.deleteLater()
        self._typing_row = None

    def _on_task_progress(self, progress: dict) -> None:
        phase = progress["phase"]
        step = progress["step"]
        if phase == "planning":
            self.busy_label.setText(f"Avaliando a próxima etapa · {step}")
        elif phase == "executing":
            self.busy_label.setText(f"Etapa {step} · executando {progress['tool']}")
        elif phase == "confirmation":
            self.busy_label.setText(f"Etapa {step} · aguardando sua confirmação")
        elif phase == "observed":
            state = "Verificado" if progress.get("verified") else "Sem confirmação do resultado"
            if not progress.get("ok"):
                state = "Falhou"
            self._add_activity(f"Etapa {step} · {progress['tool']} · {state}\n{progress.get('preview', '')}")
            key = f"{progress.get('task_id', '')}:{progress['tool']}"
            if not progress.get("ok"):
                event = self._context.emit("own_tasks", "task_failed", key, progress["tool"])
                if event:
                    self._pending_task_events[key] = event
            elif progress.get("verified") and key in self._pending_task_events:
                self._context.resolve(self._pending_task_events.pop(key))

    def _on_processing(self, busy: bool) -> None:
        if not busy:
            self._refresh_tasks()
        self._busy = busy
        self._initiative.activity()
        self.cancel_task_button.setEnabled(busy and getattr(self.controller.loop, "task_runner", None) is not None)
        self._last_interaction = time.monotonic()
        if busy:
            self._research_cancel.set()
        self.send_button.setEnabled(not busy)
        self.voice_button.setEnabled(not busy)
        self.busy_label.setVisible(busy)
        if busy:
            self._show_typing()
        else:
            self._hide_typing()
        self.chat_list.setEnabled(not busy)
        self._add_activity("Pedido em andamento" if busy else "Pedido encerrado")
        self._refresh_status()

    def _on_emotion(self, emotion: str) -> None:
        self.companion.emotion = emotion
        self.companion.update()
        self.companion_state.setText({"think": "Analisando seu pedido", "listening": "Ouvindo você", "error": "Preciso da sua atenção", "talk": "Conversando com você", "surprised": "Algo para compartilhar", "sleep": "Em repouso"}.get(emotion, "Pronta para ajudar"))

    def _on_action(self, result) -> None:
        action = result.response.action.type
        if action == "none":
            return
        status = "Aguardando confirmação" if result.needs_confirmation else ("Executado" if result.executed else "Não executado")
        tool_result = result.tool_result
        if tool_result and not tool_result.ok:
            status = "Falhou"
        self._add_activity(f"{status} · {action}")
        if tool_result:
            for agent in tool_result.meta.get("agents", [])[:2]:
                self._add_activity(f"Microagente · {agent.get('role', 'especialista')} · {'concluído' if agent.get('ok') else 'com pendência'}")

    def _add_activity(self, text: str) -> None:
        self.control_center.add_activity(text)
        self.activity.insertItem(0, f"{datetime.now().strftime('%H:%M')}   {text}")
        while self.activity.count() > 100:
            self.activity.takeItem(self.activity.count() - 1)

    def _reload_chats(self, *_args) -> None:
        self.chat_list.clear()
        for chat in self.store.list_chats(self.search.text()):
            item = QListWidgetItem(chat["title"])
            item.setData(Qt.ItemDataRole.UserRole, chat["id"])
            self.chat_list.addItem(item)
            if chat["id"] == self.chat_id:
                self.chat_list.setCurrentItem(item)

    def new_chat(self) -> None:
        if self._busy:
            self.statusBar().showMessage("Aguarde o pedido atual antes de abrir outra conversa.", 4000)
            return
        self.activate_chat(self.store.create())
        self.set_page(0)

    def activate_chat(self, chat_id: str) -> None:
        if self._busy:
            return
        self.chat_id = chat_id
        self.settings.setValue("last_chat", chat_id)
        for card in self._cards:
            self.feed_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        messages = self.store.messages(chat_id)
        self.hero.setVisible(not messages)
        for message in messages:
            self._add_card(message["role"], message["content"])
        loop = getattr(self.controller, "loop", None)
        if loop:
            loop.history = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in {"user", "assistant"}][-12:]
            if getattr(loop, "memory", None):
                loop.memory.session_id = chat_id
        self._reload_chats()

    def _rename_chat(self, item: QListWidgetItem) -> None:
        title, accepted = QInputDialog.getText(self, "Renomear conversa", "Nome", text=item.text())
        if accepted and title.strip():
            self.store.rename(item.data(Qt.ItemDataRole.UserRole), title)
            self._reload_chats()

    def _delete_chat(self) -> None:
        item = self.chat_list.currentItem()
        if not item or self._busy:
            return
        if QMessageBox.question(self, "Excluir conversa", "Excluir esta conversa da biblioteca? As memórias aprendidas são mantidas.") != QMessageBox.StandardButton.Yes:
            return
        selected = item.data(Qt.ItemDataRole.UserRole)
        self.store.delete(selected)
        if selected == self.chat_id:
            chats = self.store.list_chats()
            self.activate_chat(chats[0]["id"] if chats else self.store.create())
        self._reload_chats()

    def _scheduler(self):
        return getattr(self.controller, "_reminder_scheduler", None)

    def _refresh_reminders(self) -> None:
        selected = self.reminders.currentItem()
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.reminders.clear()
        scheduler = self._scheduler()
        if not scheduler:
            self.agenda_empty.hide()
            self.agenda_feedback.setText("Agenda indisponível nesta sessão.")
            return
        for reminder in scheduler.list_pending():
            due = datetime.fromisoformat(reminder["due_at"]).strftime("%d/%m · %H:%M")
            item = QListWidgetItem(f"{due}   {reminder['message']}")
            item.setData(Qt.ItemDataRole.UserRole, reminder["id"])
            self.reminders.addItem(item)
            if reminder["id"] == selected_id:
                self.reminders.setCurrentItem(item)
        self.agenda_empty.setVisible(self.reminders.count() == 0)

    def _add_reminder(self) -> None:
        scheduler = self._scheduler()
        if not scheduler:
            return
        try:
            scheduler.add(self.reminder_date.dateTime().toPyDateTime().astimezone().isoformat(), self.reminder_text.text())
            self.reminder_text.clear()
            self.agenda_feedback.setText("Lembrete salvo neste computador.")
            self._refresh_reminders()
        except ValueError as exc:
            self.agenda_feedback.setText(str(exc))

    def _cancel_reminder(self) -> None:
        item = self.reminders.currentItem()
        if item and self._scheduler():
            self._scheduler().cancel(item.data(Qt.ItemDataRole.UserRole))
            self._refresh_reminders()
            self.agenda_feedback.setText("Lembrete cancelado.")

    def _toggle_floating_companion(self) -> None:
        self.controller.setVisible(not self.controller.isVisible())

    def _refresh_status(self) -> None:
        self.model_badge.setText(self._model_name())
        llm = getattr(getattr(self.controller, "loop", None), "llm", None)
        self.model_badge.setToolTip(getattr(llm, "unavailable_reason", "") or "Modelo executado neste computador.")
        if not self.isVisible():
            return
        from core.runtime_budget import INFERENCE_GATE
        state = INFERENCE_GATE.telemetry()
        self.control_center.set_session(model=self._model_name(), busy=self._busy,
            blocked=self.controller.loop.registry.control.is_cancelled(),
            active=state["active"], waiting=state["waiting"])
        try:
            import psutil

            memory = psutil.virtual_memory()
            self.ram_label.setText(f"RAM · {memory.percent:.0f}% usada · {memory.available / 1024 ** 3:.1f} GiB livres")
            self.ram_bar.setValue(int(memory.percent))
            self.queue_label.setText(f"Inferência · {state['active']} ativa · {state['waiting']} aguardando")
            if self.pages.currentIndex() == 4:
                self.control_center.set_resources(cpu=psutil.cpu_percent(interval=None),
                                                   free_gib=memory.available / 1024 ** 3)
        except Exception:
            log.debug("Desktop telemetry unavailable", exc_info=True)
            self.control_center.values["resources"].setText("Indisponível")
            self.control_center.notes["resources"].setText("Não foi possível consultar o sistema")
        loop = getattr(self.controller, "loop", None)
        if loop:
            self.companion.mode = loop.mode_name
            self.mode_button.setText("Modo autônomo · temporário" if loop.mode_name == "autonoma" else "Modo assistido")
        if self.pages.currentIndex() == 1:
            self._refresh_reminders()

    def closeEvent(self, event) -> None:
        self._closing = True
        self.controller.cancel_task()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("dock_state", self.saveState())
        self.settings.sync()
        self.telemetry_timer.stop()
        self.backup_timer.stop()
        self.research_timer.stop()
        self.initiative_timer.stop()
        self._research_cancel.set()
        self.companion.timer.stop()
        self._stop_transition()
        self.controller._closing_with_desktop = True
        self.controller.close()
        super().closeEvent(event)
        self.shutdown_requested.emit()
