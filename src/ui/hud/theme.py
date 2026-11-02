"""Fonts, native window treatment and token-generated HUD styles."""
import ctypes
import sys

from app_paths import resource_path
from ui.tokens import hud_design_tokens, hud_palette


def register_fonts():
    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app.property('nyx_hud_fonts_loaded'):
        return
    for name in ('Inter.ttf', 'JetBrainsMono.ttf'):
        path = resource_path('assets/fonts')/name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setProperty('nyx_hud_fonts_loaded', True)


def native_window_style(window, theme, exclude_capture=True):
    """Only this main window: retain native frame and leave the pet capturable."""
    from PyQt6.QtWidgets import QApplication
    if sys.platform != 'win32' or QApplication.platformName() != 'windows':
        return {'dark_frame':False, 'mica':False, 'capture_excluded':False, 'supported':False}
    from ctypes import wintypes as w
    hwnd = int(window.winId())
    dwm = ctypes.WinDLL('dwmapi')
    dwm.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
    dark = w.BOOL(theme == 'midnight')
    frame = dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark)) == 0
    mica = False
    if sys.getwindowsversion().build >= 22621:
        backdrop = w.DWORD(2)
        mica = dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop)) == 0
    user = ctypes.WinDLL('user32')
    user.SetWindowDisplayAffinity.argtypes = [w.HWND, w.DWORD]
    protected = bool(user.SetWindowDisplayAffinity(hwnd, 0x11 if exclude_capture else 0))
    return {'dark_frame':frame, 'mica':mica, 'capture_excluded':protected and exclude_capture, 'supported':True}


def stylesheet(theme='midnight', accent='gold', font_size=14):
    p = hud_palette(theme)
    d = hud_design_tokens()
    accent = 'teal' if accent in {'teal','cyan','mint'} else 'gold'
    a, on = p[accent], p['onTeal' if accent=='teal' else 'onGold']
    radius = d['radius']
    return f"""
    QWidget {{ color:{p['text']}; font-family:'Inter','Segoe UI'; font-size:{font_size}px; }}
    QMainWindow#NyxDesktop, QWidget#DesktopPage, QWidget#WorkspaceSurface {{ background:{p['ink']}; }}
    QDockWidget {{ color:{p['muted']}; font-size:12px; }}
    QDockWidget::title {{ background:{p['surface1']}; padding:6px 12px; }}
    QWidget#DockBody {{ background:{p['surface1']}; }}
    QFrame#TopBar, QFrame#StatusStrip {{ background:{p['surface1']}; border-bottom:1px solid {p['line']}; }}
    QLabel#PageTitle, QLabel#SectionTitle {{ font-size:16px; font-weight:600; }}
    QLabel#HeroTitle {{ font-size:22px; font-weight:600; }}
    QLabel#Brand {{ color:{a}; font-size:19px; font-weight:600; }}
    QLabel#Muted, QLabel#MessageRole, QLabel#MetricCaption {{ color:{p['muted']}; }}
    QLabel#MessageRole, QLabel#Eyebrow, QLabel#MetricCaption, QLabel#HudData {{ font-family:'JetBrains Mono'; font-size:11px; }}
    QLabel#Eyebrow {{ color:{a}; }}
    QPushButton, QToolButton {{ background:{p['surface2']}; border:1px solid {p['line']}; border-radius:8px; padding:8px 12px; }}
    QPushButton:hover, QToolButton:hover {{ border-color:{a}; }}
    QPushButton:focus, QToolButton:focus, QLineEdit:focus, QTextEdit#Composer:focus {{ border:2px solid {a}; }}
    QPushButton:disabled {{ color:{p['muted']}; border-color:{p['line']}; }}
    QPushButton#Primary {{ background:{a}; color:{on}; border-color:{a}; font-weight:600; }}
    QPushButton#Danger {{ color:{p['red']}; background:{p['surface1']}; border-color:{p['red']}; }}
    QPushButton#Danger:hover {{ background:{p['red']}; color:{p['onRed']}; }}
    QPushButton#Nav {{ background:transparent; border-color:transparent; text-align:left; font-size:12px; padding:8px 6px; }}
    QPushButton#Nav:checked {{ color:{a}; background:{p['surface2']}; border-left:2px solid {a}; }}
    QPushButton#Quiet, QToolButton#StatusItem {{ background:transparent; border-color:transparent; color:{p['muted']}; }}
    QToolButton#StatusItem {{ font-family:'JetBrains Mono'; font-size:11px; padding:5px 9px; }}
    QToolButton#StatusItem:checked {{ color:{p['teal']}; border-color:{p['teal']}; }}
    QLineEdit, QComboBox, QSpinBox, QDateTimeEdit, QPlainTextEdit, QTextEdit#ActionDetails {{ background:{p['surface2']}; border:1px solid {p['line']}; border-radius:8px; padding:8px; selection-background-color:{a}; }}
    QComboBox QAbstractItemView {{ background:{p['surface1']}; selection-background-color:{p['surface2']}; }}
    QFrame#ComposerFrame {{ background:{p['surface1']}; border:1px solid {p['lineStrong']}; border-radius:{radius['panel']}px; }}
    QTextEdit#Composer {{ background:transparent; border:none; padding:4px; }}
    QScrollArea, QWidget#MessageFeed, QTextBrowser#MessageBody {{ background:transparent; border:none; }}
    QTextBrowser#MessageBody {{ padding:0; selection-background-color:{a}; }}
    QFrame#AssistantCard {{ background:transparent; border:none; border-left:2px solid {p['teal']}; }}
    QFrame#AssistantCard[streaming="true"] {{ border-left-color:{p['gold']}; }}
    QFrame#UserCard {{ background:{p['surface2']}; border-radius:8px; }}
    QFrame#ErrorCard {{ border-left:2px solid {p['red']}; background:{p['surface1']}; }}
    QFrame#HudActionCard, QFrame#ConfirmCard, QFrame#OverviewCard, QFrame#PalettePanel, QFrame#PermissionSurface, QFrame#Toast {{ background:{p['surface1']}; border:1px solid {p['line']}; border-radius:8px; }}
    QFrame#ConfirmCard {{ border-left:2px solid {p['gold']}; }}
    QFrame#ConfirmCard[destructive="true"] {{ border-left-color:{p['red']}; }}
    QLabel#ActionState[verified="true"] {{ color:{p['teal']}; }}
    QLabel#ActionState[verified="false"] {{ color:{p['gold']}; }}
    QPlainTextEdit#HudTrace {{ font-family:'JetBrains Mono'; font-size:12px; }}
    QListWidget {{ background:transparent; border:none; outline:none; }}
    QListWidget::item {{ padding:8px; border-radius:8px; }}
    QListWidget::item:selected, QListWidget::item:hover {{ background:{p['surface2']}; color:{p['text']}; }}
    QFrame[frameShape="4"] {{ color:{p['line']}; }}
    QProgressBar {{ border:none; background:{p['surface2']}; min-height:5px; max-height:5px; border-radius:2px; }}
    QProgressBar::chunk {{ background:{p['teal']}; }}
    QCheckBox {{ spacing:8px; padding:7px 0; }}
    QCheckBox::indicator {{ width:17px; height:17px; border:1px solid {p['muted']}; border-radius:4px; }}
    QCheckBox::indicator:checked {{ background:{a}; border-color:{a}; }}
    QSlider::groove:horizontal {{ height:4px; background:{p['line']}; }}
    QSlider::handle:horizontal {{ width:14px; margin:-5px 0; background:{a}; border-radius:7px; }}
    QTabWidget::pane {{ border:none; background:{p['surface1']}; }}
    QTabBar::tab {{ color:{p['muted']}; background:{p['surface1']}; padding:10px 12px; border:1px solid {p['line']}; }}
    QTabBar::tab:selected {{ color:{a}; background:{p['surface2']}; border-bottom:2px solid {a}; }}
    QMenu {{ background:{p['surface1']}; border:1px solid {p['line']}; padding:4px; }}
    QMenu::item {{ padding:8px 16px; }}
    QMenu::item:selected {{ background:{p['surface2']}; }}
    QScrollBar:vertical {{ width:8px; background:transparent; }}
    QScrollBar::handle:vertical {{ background:{p['lineStrong']}; border-radius:4px; min-height:30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
    QFrame#TypingBubble {{ background:{p['surface1']}; border-left:2px solid {p['gold']}; border-radius:8px; }}
    QLabel#TypingText, QLabel#TypingDots {{ color:{p['gold']}; }}
    QLabel#Badge, QLabel#StateBanner {{ background:{p['surface2']}; padding:6px; border-radius:8px; }}
    QPushButton#OverviewRoute, QPushButton#Suggestion {{ background:{p['surface1']}; text-align:left; padding:14px; }}
    QTextBrowser#StudyPreview, QTableWidget {{ background:{p['surface2']}; border:1px solid {p['line']}; padding:8px; }}
    QHeaderView::section {{ background:{p['surface1']}; color:{p['muted']}; padding:8px; }}
    QStatusBar {{ background:{p['surface1']}; color:{p['muted']}; font-size:11px; }}
    """
