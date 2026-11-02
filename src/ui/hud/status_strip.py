"""Compact controls expose current state, without fabricated telemetry."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QPushButton, QSizePolicy


class StatusStrip(QFrame):
    requested = pyqtSignal(str)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('StatusStrip')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12,4,12,4)
        layout.setSpacing(4)
        self.items = {}
        for key, label in (('model','MODELO'),('profile','PERFIL'),('permission','PERMISSÃO'),('presence','PRESENÇA')):
            button = QToolButton()
            button.setObjectName('StatusItem')
            button.setText(label)
            button.setAccessibleName(label.capitalize())
            button.clicked.connect(lambda checked=False, route=key:self.requested.emit(route))
            layout.addWidget(button, 2 if key=='model' else 1)
            self.items[key] = button
        self.items['model'].setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.stop = QPushButton('PARAR')
        self.stop.setObjectName('Danger')
        self.stop.setAccessibleName('Interromper todas as ações da Nyx')
        self.stop.clicked.connect(self.stop_requested)
        layout.addWidget(self.stop)

    def update_state(self, *, model, profile, permission, private):
        values = {'model':'MODELO '+model.removeprefix('Local · '), 'profile':profile.upper(),
                  'permission':'ASSISTIDA' if permission=='assistida' else 'AUTÔNOMA',
                  'presence':'PRIVADO' if private else 'PRESENÇA'}
        for key, value in values.items():
            button = self.items[key]
            button.setToolTip(value)
            button.setText(button.fontMetrics().elidedText(value, Qt.TextElideMode.ElideRight,
                                                          max(60,button.width()-18)))

