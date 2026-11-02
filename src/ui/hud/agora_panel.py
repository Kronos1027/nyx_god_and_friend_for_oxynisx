"""A passive view of authorized observations; opening it never starts sensors."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton, QProgressBar


class AgoraPanel(QFrame):
    privacy_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        title = QLabel('AGORA')
        title.setObjectName('Eyebrow')
        layout.addWidget(title)
        self.fields = {}
        for key, caption in (('window','JANELA ATIVA'),('media','MÍDIA'),('game','JOGO'),
                             ('processes','PROCESSOS'),('task','TAREFA')):
            label = QLabel(caption)
            label.setObjectName('HudData')
            layout.addWidget(label)
            value = QLabel('Desligado · configure percepção' if key!='task' else 'Nenhuma tarefa em andamento')
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            value.setAccessibleName(caption.capitalize())
            layout.addWidget(value)
            self.fields[key] = value
        self.stepper = QLabel('')
        self.stepper.setObjectName('Muted')
        self.stepper.setWordWrap(True)
        layout.addWidget(self.stepper)
        self.cancel = QPushButton('Cancelar tarefa')
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_requested)
        layout.addWidget(self.cancel)
        self.resources = QLabel('Recursos: aguardando consulta do motor')
        self.resources.setObjectName('HudData')
        self.resources.setWordWrap(True)
        layout.addWidget(self.resources)
        self.memory = QProgressBar()
        self.memory.setRange(0,100)
        self.memory.setTextVisible(False)
        self.memory.setAccessibleName('Uso da memória do sistema')
        layout.addWidget(self.memory)
        self.privacy = QPushButton('Configurar percepção')
        self.privacy.clicked.connect(self.privacy_requested)
        layout.addWidget(self.privacy)

    def set_private(self, enabled):
        self.clear_presence('Pausado no Modo Privado' if enabled else 'Aguardando consulta autorizada')

    def clear_presence(self, reason):
        for key in ('window','media','game','processes'):
            self.fields[key].setText(reason)
            self.fields[key].setToolTip(reason)

    def set_presence(self, snapshot):
        for key, value in snapshot.get('fields', {}).items():
            if key in self.fields and key != 'task':
                self.fields[key].setText(value['text'])
                self.fields[key].setToolTip(
                    'Observação local efêmera; não salva em histórico. '
                    'Janela/jogo/processos: consulta em até 6 s; mídia: até 12 s. '
                    'Jogos: lista limitada por nome de processo. Mídia: sessão publicada no Windows. '
                    f"Estado: {value['status']}.")

    def progress(self, data):
        phase = data.get('phase')
        number = data.get('step',0)
        label = {'planning':'Planejando','executing':'Executando','confirmation':'Aguardando confirmação',
                 'conversation_delta':'Conversando','observed':'Resultado observado'}.get(phase,'Em andamento')
        self.fields['task'].setText(label)
        if number:
            self.stepper.setText(f"Etapa {number} · {data.get('tool','resposta')}")
        self.cancel.setEnabled(True)

    def set_busy(self, busy):
        self.cancel.setEnabled(busy)
        if not busy:
            self.fields['task'].setText('Nenhuma tarefa em andamento')
            self.stepper.clear()

