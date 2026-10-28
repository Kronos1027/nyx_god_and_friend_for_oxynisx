"""Native overview of real Nyx state, with routes to the existing controls."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
                            QLabel, QPushButton, QScrollArea, QListWidget)


class ControlCenter(QWidget):
    requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DesktopPage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("DesktopPage")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(18)
        eyebrow = QLabel("NYX / CENTRAL")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Seu espaço com a Nyx")
        title.setObjectName("HeroTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        subtitle = QLabel("Converse, acompanhe seu trabalho e escolha o que a Nyx pode observar.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("Muted")
        layout.addWidget(subtitle)
        toolbar = QHBoxLayout()
        chat = QPushButton("Iniciar conversa  ↗")
        chat.setObjectName("Primary")
        chat.clicked.connect(lambda: self.requested.emit("chat"))
        toolbar.addWidget(chat)
        self.resume_button = QPushButton("Retomar ferramentas")
        self.resume_button.clicked.connect(lambda: self.requested.emit("resume"))
        self.resume_button.hide()
        toolbar.addWidget(self.resume_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.status = QLabel("Consultando o estado da sessão…")
        self.status.setWordWrap(True)
        self.status.setObjectName("StateBanner")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.metrics = QGridLayout()
        self.metric_cards, self.values, self.notes = [], {}, {}
        for key, caption in (("model", "MODELO LOCAL"), ("resources", "RECURSOS"), ("tasks", "TAREFAS")):
            card = QFrame()
            card.setObjectName("OverviewCard")
            column = QVBoxLayout(card)
            column.setContentsMargins(16, 15, 16, 15)
            label = QLabel(caption)
            label.setObjectName("MetricCaption")
            value = QLabel("—")
            value.setObjectName("MetricValue")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            note = QLabel("Ainda sem leitura")
            note.setObjectName("Muted")
            note.setTextFormat(Qt.TextFormat.PlainText)
            note.setWordWrap(True)
            note.setMinimumHeight(42)
            for widget in (label, value, note):
                column.addWidget(widget)
            self.values[key], self.notes[key] = value, note
            self.metric_cards.append(card)
        layout.addLayout(self.metrics)
        section = QLabel("Continue de onde precisar")
        section.setObjectName("SectionTitle")
        layout.addWidget(section)
        self.routes = QGridLayout()
        self.route_buttons = {}
        for key, title, description in (
            ("tasks", "Atividades e tarefas", "Veja etapas, pendências e retomadas."),
            ("studio", "Estúdio de criação", "Projetos, arquivos, versões e habilidades."),
            ("memory", "Memória e interesses", "Revise, corrija ou apague seus registros."),
            ("privacy", "Sensores e privacidade", "Escolha o que pode ser observado."),
            ("agenda", "Agenda", "Organize e acompanhe seus lembretes."),
            ("performance", "Desempenho", "Consulte CPU, RAM e GPU disponíveis."),
        ):
            button = QPushButton(f"{title}  ↗\n{description}")
            button.setObjectName("OverviewRoute")
            button.setAccessibleName(title)
            button.clicked.connect(lambda _checked=False, route=key: self.requested.emit(route))
            self.route_buttons[key] = button
        layout.addLayout(self.routes)
        activity_title = QLabel("Nesta sessão")
        activity_title.setObjectName("SectionTitle")
        layout.addWidget(activity_title)
        self.activity = QListWidget()
        self.activity.setWordWrap(True)
        self.activity.setMinimumHeight(100)
        self.activity.setMaximumHeight(180)
        self.activity.addItem("As ações aparecerão aqui quando ocorrerem.")
        layout.addWidget(self.activity)
        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self._columns = None
        self._arrange(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(2 if self.width() >= 720 else 1)

    def _arrange(self, columns):
        if columns == self._columns:
            return
        self._columns = columns
        for grid in (self.metrics, self.routes):
            while grid.count():
                grid.takeAt(0)
        metric_columns = 3 if columns == 2 else 1
        for index, card in enumerate(self.metric_cards):
            self.metrics.addWidget(card, index // metric_columns, index % metric_columns)
        for index, button in enumerate(self.route_buttons.values()):
            self.routes.addWidget(button, index // columns, index % columns)

    def set_session(self, *, model, busy, blocked, active, waiting):
        self.values["model"].setText(model)
        self.notes["model"].setText(f"Inferência: {active} ativa · {waiting} aguardando")
        self.status.setText("Ferramentas interrompidas. Retome quando estiver pronto." if blocked else
                            "Pedido em andamento. Acompanhe as etapas em Atividades." if busy else
                            "Disponível para seu próximo pedido.")
        self.resume_button.setVisible(blocked)

    def set_resources(self, *, cpu, free_gib):
        self.values["resources"].setText(f"{free_gib:.1f} GiB livres")
        self.notes["resources"].setText(f"CPU {cpu:.0f}% · RAM do sistema · GPU em Desempenho")

    def set_tasks(self, total, pending):
        self.values["tasks"].setText(f"{pending} para revisar")
        self.notes["tasks"].setText(f"{total} no histórico local")

    def add_activity(self, text):
        if self.activity.count() == 1 and self.activity.item(0).data(Qt.ItemDataRole.UserRole) is None:
            self.activity.clear()
        self.activity.insertItem(0, text)
        self.activity.item(0).setData(Qt.ItemDataRole.UserRole, True)
        while self.activity.count() > 6:
            self.activity.takeItem(self.activity.count() - 1)
