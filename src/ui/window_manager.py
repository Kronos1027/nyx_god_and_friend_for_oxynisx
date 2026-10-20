"""Nyx — ui/window_manager.py (Gerenciador de Janelas Generativas do Grande Sábio)

Permite que a Nyx crie, atualize e feche janelas dinâmicas declarativas (HUDs,
gráficos, planos ao vivo, terminais, tabelas e visualizações de código).

Recursos:
- Frameless, translúcida, always-on-top opcional
- Validação estrita de componentes declarativos (SEM execução de código arbitrário)
- Temas nativos via tokens (Nyx Neon, Anime Cyber, Minimal)
- Olho de controle (halo/crosshair visual antes de clicar)
- Execução thread-safe via sinais Qt
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ui.tokens import get_theme, generate_stylesheet

log = logging.getLogger(__name__)


class GenerativeWindow(QWidget):
    """Janela dinâmica renderizada a partir de uma especificação JSON."""

    def __init__(self, spec: Dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.window_id = spec.get("id") or f"win_{uuid.uuid4().hex[:8]}"
        self.spec = spec
        self.theme = get_theme(spec.get("theme", "nyx_neon"))
        self._drag_pos = QPoint()
        self._components: Dict[str, QWidget] = {}

        # Configurações de Janela
        self.setObjectName("GenerativeWindowRoot")
        flags = Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
        if spec.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(generate_stylesheet(self.theme))

        w = int(spec.get("width", 500))
        h = int(spec.get("height", 420))
        self.resize(w, h)

        if "x" in spec and "y" in spec:
            self.move(int(spec["x"]), int(spec["y"]))

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Root Card Frame
        root_card = QFrame(self)
        root_card.setObjectName("GenerativeWindowRoot")
        root_layout = QVBoxLayout(root_card)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)
        main_layout.addWidget(root_card)

        # Header Bar (Título e Fechar)
        header = QFrame(root_card)
        header.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)

        title_lbl = QLabel(self.spec.get("title", "Nyx Generative Window"), header)
        title_lbl.setObjectName("WindowTitle")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        close_btn = QPushButton("✕", header)
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #94A3B8; font-size: 13px; border: none; }"
            "QPushButton:hover { color: #FF0055; font-weight: bold; }"
        )
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)

        root_layout.addWidget(header)

        # Scroll Area para Conteúdo
        scroll = QScrollArea(root_card)
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setObjectName("ScrollContainer")
        self.content_layout = QVBoxLayout(container)
        self.content_layout.setContentsMargins(4, 8, 4, 8)
        self.content_layout.setSpacing(10)

        # Renderiza componentes iniciais
        for comp in self.spec.get("components", []):
            widget = self._render_component(comp)
            if widget:
                cid = comp.get("id") or f"comp_{len(self._components)}"
                self._components[cid] = widget
                self.content_layout.addWidget(widget)

        self.content_layout.addStretch()
        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def _render_component(self, comp: Dict[str, Any]) -> Optional[QWidget]:
        ctype = str(comp.get("type", "text")).lower()
        frame = QFrame()
        frame.setObjectName("CardComponent")
        card_layout = QVBoxLayout(frame)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        if "title" in comp:
            t_lbl = QLabel(str(comp["title"]))
            t_lbl.setObjectName("CompTitle")
            card_layout.addWidget(t_lbl)

        if ctype == "text":
            lbl = QLabel(str(comp.get("value", "")))
            lbl.setObjectName("CompText")
            lbl.setWordWrap(True)
            card_layout.addWidget(lbl)

        elif ctype == "markdown":
            browser = QTextBrowser()
            browser.setMarkdown(str(comp.get("value", "")))
            browser.setMaximumHeight(int(comp.get("max_height", 200)))
            card_layout.addWidget(browser)

        elif ctype == "code":
            edit = QPlainTextEdit()
            edit.setPlainText(str(comp.get("value", "")))
            edit.setReadOnly(True)
            edit.setMaximumHeight(int(comp.get("max_height", 220)))
            card_layout.addWidget(edit)

        elif ctype == "progress":
            pbar = QProgressBar()
            pbar.setValue(int(comp.get("value", 0)))
            pbar.setMaximum(int(comp.get("max", 100)))
            card_layout.addWidget(pbar)

        elif ctype == "table":
            headers = comp.get("headers", [])
            rows = comp.get("rows", [])
            table = QTableWidget(len(rows), len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for r_idx, row in enumerate(rows):
                for c_idx, val in enumerate(row):
                    table.setItem(r_idx, c_idx, QTableWidgetItem(str(val)))
            table.setMaximumHeight(int(comp.get("max_height", 200)))
            card_layout.addWidget(table)

        elif ctype == "chart":
            # Gráfico de barras simples baseado em percentuais
            data = comp.get("data", {})
            for key, val in data.items():
                row_h = QHBoxLayout()
                k_lbl = QLabel(f"{key}:")
                k_lbl.setFixedWidth(90)
                k_lbl.setStyleSheet("font-size: 11px; color: #94A3B8;")
                bar = QProgressBar()
                bar.setValue(int(val))
                bar.setMaximum(100)
                bar.setFixedHeight(12)
                row_h.addWidget(k_lbl)
                row_h.addWidget(bar)
                card_layout.addLayout(row_h)

        elif ctype == "steps":
            # Checklist de passos ao vivo
            steps = comp.get("steps", [])
            for s in steps:
                s_box = QHBoxLayout()
                status = s.get("status", "pending")
                icon = "⏳" if status == "pending" else "⚡" if status == "running" else "✅" if status == "success" else "❌"
                s_lbl = QLabel(f"{icon} {s.get('name', '')}")
                s_lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
                s_box.addWidget(s_lbl)
                card_layout.addLayout(s_box)

        elif ctype == "terminal_log":
            term = QPlainTextEdit()
            term.setReadOnly(True)
            term.setStyleSheet("background: #050811; color: #00FF66; font-family: Consolas; font-size: 11px;")
            term.setPlainText(str(comp.get("value", "")))
            term.setMaximumHeight(int(comp.get("max_height", 160)))
            card_layout.addWidget(term)

        elif ctype == "input":
            inp = QLineEdit()
            inp.setPlaceholderText(comp.get("placeholder", "Digite algo..."))
            card_layout.addWidget(inp)

        elif ctype == "button":
            btn = QPushButton(comp.get("label", "Executar"))
            card_layout.addWidget(btn)

        elif ctype == "telemetry":
            # Mini painel de GPU/CPU/RAM
            try:
                import psutil
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                info = f"CPU: {cpu}% | RAM: {ram}%"
            except Exception:
                info = "Telemetria ativa"
            lbl = QLabel(info)
            lbl.setStyleSheet("font-weight: bold; color: #00F0FF; font-size: 12px;")
            card_layout.addWidget(lbl)

        else:
            lbl = QLabel(f"Componente '{ctype}' não suportado.")
            card_layout.addWidget(lbl)

        return frame

    def update_component(self, comp_id: str, patch: Dict[str, Any]) -> bool:
        """Atualiza valores de um componente existente dinamicamente."""
        comp_widget = self._components.get(comp_id)
        if not comp_widget:
            return False

        # Busca widget interno dentro do layout do componente
        layout = comp_widget.layout()
        if not layout:
            return False

        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget()
            if isinstance(w, QLabel) and "value" in patch and w.objectName() == "CompText":
                w.setText(str(patch["value"]))
                return True
            elif isinstance(w, QProgressBar) and "value" in patch:
                w.setValue(int(patch["value"]))
                return True
            elif isinstance(w, QPlainTextEdit) and "value" in patch:
                if patch.get("append", False):
                    w.appendPlainText(str(patch["value"]))
                else:
                    w.setPlainText(str(patch["value"]))
                return True
            elif isinstance(w, QTextBrowser) and "value" in patch:
                w.setMarkdown(str(patch["value"]))
                return True

        return True

    # Suporte a arraste da janela
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()


class ControlHalo(QWidget):
    """Olho de controle: halo/crosshair visual antes de clicar."""

    def __init__(self, x: int, y: int, duration_ms: int = 1200) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(80, 80)
        self.move(x - 40, y - 40)
        self._radius = 10
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)
        QTimer.singleShot(duration_ms, self.close)
        self.show()

    def _animate(self) -> None:
        self._radius = (self._radius + 2) % 36
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#00F0FF"), 2)
        painter.setPen(pen)
        painter.drawEllipse(40 - self._radius, 40 - self._radius, self._radius * 2, self._radius * 2)
        painter.drawEllipse(38, 38, 4, 4)


class WindowManagerSignals(QObject):
    spawn_requested = pyqtSignal(dict)
    update_requested = pyqtSignal(str, dict)
    close_requested = pyqtSignal(str)


class WindowManager:
    """Gerenciador central de janelas da Nyx."""

    _instance: Optional[WindowManager] = None

    @classmethod
    def get_instance(cls) -> WindowManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.windows: Dict[str, GenerativeWindow] = {}
        self.signals = WindowManagerSignals()
        self.signals.spawn_requested.connect(self._on_spawn)
        self.signals.update_requested.connect(self._on_update)
        self.signals.close_requested.connect(self._on_close)

    def spawn(self, spec: Dict[str, Any]) -> str:
        """Cria e abre uma nova janela declarativa."""
        win_id = spec.get("id") or f"win_{uuid.uuid4().hex[:8]}"
        spec["id"] = win_id
        app = QApplication.instance()
        if app:
            self._on_spawn(spec)
        return win_id

    def update(self, window_id: str, patch: Dict[str, Any]) -> bool:
        """Atualiza uma janela existente."""
        if window_id not in self.windows:
            return False
        self.windows[window_id].update_component(patch.get("component_id", ""), patch)
        return True

    def close(self, window_id: str) -> bool:
        """Fecha e descarta a janela especificada."""
        win = self.windows.pop(window_id, None)
        if win:
            win.close()
            return True
        return False

    def list_windows(self) -> List[Dict[str, Any]]:
        """Retorna as janelas ativas gerenciadas pela Nyx."""
        return [
            {"id": wid, "title": win.spec.get("title", "Sem título")}
            for wid, win in self.windows.items()
        ]

    def _on_spawn(self, spec: Dict[str, Any]) -> None:
        try:
            win = GenerativeWindow(spec)
            self.windows[win.window_id] = win
            win.show()
        except Exception as exc:
            log.error("Erro ao instanciar GenerativeWindow: %s", exc)

    def _on_update(self, window_id: str, patch: Dict[str, Any]) -> None:
        self.update(window_id, patch)

    def _on_close(self, window_id: str) -> None:
        self.close(window_id)

    def show_control_halo(self, x: int, y: int, duration_ms: int = 1000) -> None:
        """Exibe o halo visual de controle (olho de controle) nas coordenadas (x, y)."""
        app = QApplication.instance()
        if app:
            ControlHalo(x, y, duration_ms)
