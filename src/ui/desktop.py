"""Native conversation workspace with persistent chats and movable panels."""

from __future__ import annotations

import logging
import threading
import shutil
import time
from datetime import datetime

from PyQt6.QtCore import QDateTime, QEasingCurve, QPropertyAnimation, QRectF, QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QCursor, QColor, QDesktopServices, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDockWidget, QFormLayout,
    QFileDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSlider, QStackedWidget, QTextBrowser, QTextEdit,
    QToolButton, QVBoxLayout, QWidget, QSizePolicy, QTabWidget,
)

from app_paths import user_data_dir
from ui.chat_store import ChatStore
from ui.desktop_theme import ACCENTS, desktop_stylesheet
from ui.sprite_renderer import SpriteRenderer

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
        self.chat_id = ""
        self._busy = False
        self._research_busy = False
        self._closing = False
        self._research_cancel = threading.Event()
        self._last_interaction = time.monotonic()
        self._cards: list[QWidget] = []
        self._animation: QPropertyAnimation | None = None
        self._animated_page: QWidget | None = None
        self._build_center()
        self._build_sidebar()
        self._build_companion()
        self._build_activity()
        self._build_menu()
        self._connect_controller()
        self._apply_preferences()
        self._restore_layout()
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
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_chat)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=lambda: self.search.setFocus())

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Muted")
        label.setWordWrap(True)
        return label

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
        header.addWidget(self.page_title)
        header.addStretch()
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
        root.addWidget(bar)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self._build_chat_page()
        self._build_agenda_page()
        self._build_settings_page()
        self._build_evolution_page()

    def _toggle_focus(self, enabled: bool) -> None:
        docks = (self.sidebar, self.companion_dock, self.activity_dock)
        if enabled:
            self._focus_visibility = [dock.isVisible() for dock in docks]
            for dock in docks:
                dock.hide()
        else:
            for dock, visible in zip(docks, getattr(self, "_focus_visibility", [True] * 3), strict=True):
                dock.setVisible(visible)

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
        brand = QLabel("nyx ✧")
        brand.setObjectName("Brand")
        layout.addWidget(brand)
        layout.addWidget(self._muted("Uma companhia. Muitas possibilidades."))
        new_button = QPushButton("+  Nova conversa")
        new_button.setObjectName("Primary")
        new_button.clicked.connect(self.new_chat)
        layout.addWidget(new_button)
        self.nav_buttons = []
        for index, title in enumerate(("◌  Conversa", "◷  Agenda", "⚙  Personalizar", "✧  Aprendizado")):
            button = QPushButton(title)
            button.setObjectName("Nav")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, i=index: self.set_page(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)
        layout.addSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar conversas  Ctrl+K")
        self.search.textChanged.connect(self._reload_chats)
        layout.addWidget(self.search)
        self.chat_list = QListWidget()
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.chat_list.setAccessibleName("Histórico de conversas")
        self.chat_list.itemClicked.connect(lambda item: self.activate_chat(item.data(Qt.ItemDataRole.UserRole)))
        self.chat_list.itemDoubleClicked.connect(self._rename_chat)
        layout.addWidget(self.chat_list, 1)
        remove = QPushButton("Excluir conversa selecionada")
        remove.setObjectName("Quiet")
        remove.clicked.connect(self._delete_chat)
        layout.addWidget(remove)
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
        self.pages.addWidget(page)

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
                or self._research_busy or time.monotonic() - self._last_interaction < 60):
            return
        try:
            import psutil
            if psutil.virtual_memory().available < 2 * 1024 ** 3 or psutil.cpu_percent() > 85:
                self.research_status.setText("Estudo adiado para liberar recursos ao computador.")
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
        self.reminders = QListWidget()
        self.reminders.setWordWrap(True)
        layout.addWidget(self.reminders, 1)
        cancel = QPushButton("Cancelar lembrete selecionado")
        cancel.clicked.connect(self._cancel_reminder)
        layout.addWidget(cancel)
        self.agenda_feedback = self._muted("")
        layout.addWidget(self.agenda_feedback)
        self.pages.addWidget(page)

    def _build_settings_page(self) -> None:
        page, outer = self._page()
        self.settings_tabs = QTabWidget()
        outer.addWidget(self.settings_tabs)
        layout = self._tab_section(self.settings_tabs, "Aparência e voz")
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
        form.addRow(self.speech_check)
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
        for key, value in (("theme", theme), ("accent", accent), ("font_size", self.font_slider.value()), ("motion", self.motion_check.isChecked()), ("speech", self.speech_check.isChecked())):
            self.settings.setValue(key, value)

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

    def set_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText(("Conversa", "Sua agenda", "Do seu jeito", "Aprendizado e recuperação")[index])
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if index == 1:
            self._refresh_reminders()
        elif index == 3:
            self._refresh_learning()
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

    def _on_message(self, role: str, text: str) -> None:
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

    def _on_processing(self, busy: bool) -> None:
        self._busy = busy
        self.cancel_task_button.setEnabled(busy and getattr(self.controller.loop, "task_runner", None) is not None)
        self._last_interaction = time.monotonic()
        if busy:
            self._research_cancel.set()
        self.send_button.setEnabled(not busy)
        self.voice_button.setEnabled(not busy)
        self.busy_label.setVisible(busy)
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
            self.agenda_feedback.setText("Agenda indisponível nesta sessão.")
            return
        for reminder in scheduler.list_pending():
            due = datetime.fromisoformat(reminder["due_at"]).strftime("%d/%m · %H:%M")
            item = QListWidgetItem(f"{due}   {reminder['message']}")
            item.setData(Qt.ItemDataRole.UserRole, reminder["id"])
            self.reminders.addItem(item)
            if reminder["id"] == selected_id:
                self.reminders.setCurrentItem(item)

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
        try:
            import psutil
            from core.runtime_budget import INFERENCE_GATE

            memory = psutil.virtual_memory()
            self.ram_label.setText(f"RAM · {memory.percent:.0f}% usada · {memory.available / 1024 ** 3:.1f} GiB livres")
            self.ram_bar.setValue(int(memory.percent))
            state = INFERENCE_GATE.telemetry()
            self.queue_label.setText(f"Inferência · {state['active']} ativa · {state['waiting']} aguardando")
        except Exception:
            log.debug("Desktop telemetry unavailable", exc_info=True)
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
        self._research_cancel.set()
        self.companion.timer.stop()
        self._stop_transition()
        self.controller._closing_with_desktop = True
        self.controller.close()
        super().closeEvent(event)
        self.shutdown_requested.emit()
