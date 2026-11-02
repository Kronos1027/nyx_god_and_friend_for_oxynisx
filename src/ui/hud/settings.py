"""Searchable groups reuse the existing preference controls and persistence."""
import unicodedata
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLineEdit, QComboBox, QLabel, QPushButton


def _key(text):
    return unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().casefold()


def organize_settings(window, outer):
    tabs = window.settings_tabs
    appearance, routine, system, voice, model = [tabs.widget(index) for index in range(tabs.count())]
    tabs.clear()
    joined = QWidget()
    joined.setObjectName('DesktopPage')
    joined_layout = QVBoxLayout(joined)
    joined_layout.setContentsMargins(0,0,0,0)
    for scroll in (system,model):
        body = scroll.takeWidget()
        joined_layout.addWidget(body)
        scroll.deleteLater()
    resources = QScrollArea()
    resources.setWidgetResizable(True)
    resources.setWidget(joined)
    privacy = QPushButton('Escolher sensores e consultar acessos')
    privacy.clicked.connect(lambda:window._open_center_route('privacy'))
    routine.widget().layout().insertWidget(0,privacy)
    advanced, layout = window._page()
    layout.addWidget(window._muted('Diagnóstico e recuperação local. Cada operação mantém suas confirmações próprias.'))
    for title,callback in [('Diagnosticar memória',window._show_resource_diagnostics),
                           ('Estado das ferramentas',lambda:window._open_center_route('tool_health')),
                           ('Backups locais',lambda:_backups(window)),
                           ('Restaurar organização dos painéis',window._reset_layout)]:
        button = QPushButton(title)
        button.setAccessibleName(title)
        button.clicked.connect(callback)
        layout.addWidget(button)
    layout.addStretch()
    advanced_scroll = QScrollArea()
    advanced_scroll.setWidgetResizable(True)
    advanced_scroll.setWidget(advanced)
    for title,page in [('Geral',appearance),('Modelo e recursos',resources),('Permissões e privacidade',routine),
                       ('Voz',voice),('Avançado',advanced_scroll)]:
        tabs.addTab(page,title)
    tabs.tabBar().hide()
    navigation = QWidget()
    row = QHBoxLayout(navigation)
    row.setContentsMargins(0,0,0,0)
    search = QLineEdit()
    search.setPlaceholderText('Buscar configuração…')
    search.setClearButtonEnabled(True)
    search.setAccessibleName('Buscar configuração')
    selector = QComboBox()
    selector.setAccessibleName('Grupo de configurações')
    selector.setMinimumContentsLength(20)
    row.addWidget(search,1)
    row.addWidget(selector,1)
    outer.insertWidget(0,navigation)
    window.settings_search = search
    window.settings_section = selector
    def choose():
        index = selector.currentData()
        if isinstance(index,int):
            tabs.setCurrentIndex(index)
    def refresh(text):
        query = _key(text.strip())
        selector.blockSignals(True)
        selector.clear()
        for index in range(tabs.count()):
            labels = ' '.join(label.text() for label in tabs.widget(index).findChildren(QLabel))
            if not query or query in _key(tabs.tabText(index)+' '+labels):
                selector.addItem(tabs.tabText(index),index)
        if not selector.count():
            selector.addItem('Nenhuma opção encontrada',None)
        selected = selector.findData(tabs.currentIndex())
        selector.setCurrentIndex(max(0,selected))
        selector.blockSignals(False)
        choose()
    selector.currentIndexChanged.connect(choose)
    search.textChanged.connect(refresh)
    tabs.currentChanged.connect(lambda index:selector.setCurrentIndex(selector.findData(index)))
    refresh('')


def _backups(window):
    window.set_page(3)
    for index in range(window.learning_tabs.count()):
        if 'backup' in window.learning_tabs.tabText(index).casefold():
            window.learning_tabs.setCurrentIndex(index)
            break
