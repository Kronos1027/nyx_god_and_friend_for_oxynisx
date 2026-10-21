"""Themes for the native, dockable Nyx desktop workspace."""

PALETTES = {
    "midnight": {"bg": "#101116", "panel": "#171920", "card": "#20232d", "text": "#f1f2f7", "muted": "#9da3b5", "line": "#303440"},
    "aurora": {"bg": "#101724", "panel": "#141f30", "card": "#1c2b42", "text": "#f0f5ff", "muted": "#9cacc4", "line": "#2d405b"},
    "daylight": {"bg": "#f6f7fb", "panel": "#ffffff", "card": "#e9edf5", "text": "#192235", "muted": "#536179", "line": "#d6ddea"},
}

ACCENTS = {"violet": "#b2a1ff", "cyan": "#65d9e9", "mint": "#77deb7", "amber": "#f0c777"}


def desktop_stylesheet(theme: str = "midnight", accent: str = "violet", font_size: int = 14) -> str:
    p = PALETTES.get(theme, PALETTES["midnight"])
    a = ACCENTS.get(accent, ACCENTS["violet"])
    ink = {"violet": "#6650c8", "cyan": "#087f91", "mint": "#187955", "amber": "#8a6512"}.get(accent, "#6650c8") if theme == "daylight" else a
    return f"""
    QMainWindow#NyxDesktop, QWidget#DesktopPage {{ background: {p['bg']}; }}
    QWidget {{ color: {p['text']}; font-family: 'Segoe UI'; font-size: {font_size}px; }}
    QDockWidget {{ background: {p['panel']}; border: none; }}
    QDockWidget::title {{ background: {p['panel']}; color: {p['muted']}; padding: 10px 14px; font-size: 11px; }}
    QMainWindow::separator {{ background: {p['line']}; width: 2px; height: 2px; }}
    QWidget#DockBody, QWidget#Sidebar {{ background: {p['panel']}; }}
    QFrame#TopBar {{ background: {p['bg']}; border-bottom: 1px solid {p['line']}; }}
    QLabel#Brand {{ font-size: 24px; font-weight: 700; color: {ink}; }}
    QLabel#PageTitle {{ font-size: 22px; font-weight: 600; }}
    QLabel#HeroTitle {{ font-size: 32px; font-weight: 600; }}
    QLabel#Eyebrow {{ color: {ink}; font-size: 11px; letter-spacing: 2px; font-weight: 600; }}
    QLabel#Muted, QLabel#MessageRole {{ color: {p['muted']}; }}
    QLabel#MessageRole {{ font-size: 11px; font-weight: 600; }}
    QLabel#Badge {{ background: {p['card']}; color: {ink}; padding: 6px 12px; border-radius: 12px; font-size: 11px; }}
    QPushButton, QToolButton {{ background: {p['card']}; border: 1px solid transparent; border-radius: 9px; padding: 9px 13px; }}
    QPushButton:hover, QToolButton:hover {{ border: 1px solid {a}; }}
    QPushButton:disabled {{ color: {p['muted']}; }}
    QPushButton#Primary {{ background: {a}; color: #151a25; font-weight: 700; }}
    QPushButton#Nav {{ text-align: left; background: transparent; padding: 11px 14px; }}
    QPushButton#Nav:checked {{ background: {p['card']}; color: {ink}; }}
    QPushButton#Quiet {{ background: transparent; color: {p['muted']}; padding: 4px 8px; font-size: 11px; }}
    QPushButton#Suggestion {{ background: {p['panel']}; border: 1px solid {p['line']}; text-align: left; padding: 16px; }}
    QLineEdit, QTextEdit#Composer, QComboBox, QDateTimeEdit {{ background: {p['card']}; border: 1px solid {p['line']}; border-radius: 9px; padding: 9px; selection-background-color: {a}; }}
    QLineEdit:focus, QTextEdit#Composer:focus {{ border: 1px solid {a}; }}
    QFrame#ComposerFrame {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 18px; }}
    QTextEdit#Composer {{ background: transparent; border: none; padding: 8px; }}
    QScrollArea, QWidget#MessageFeed {{ background: transparent; border: none; }}
    QFrame#AssistantCard {{ background: transparent; border: none; }}
    QFrame#UserCard {{ background: {p['card']}; border-radius: 15px; }}
    QFrame#ErrorCard {{ background: {p['card']}; border-left: 3px solid #e58a96; border-radius: 10px; }}
    QTextBrowser#MessageBody {{ background: transparent; border: none; padding: 0px; selection-background-color: {a}; }}
    QTextBrowser#StudyPreview {{ background: {p['card']}; color: {p['text']}; border: 1px solid {p['line']}; border-radius: 9px; padding: 10px; selection-background-color: {a}; }}
    QListWidget {{ background: transparent; border: none; outline: none; }}
    QListWidget::item {{ padding: 11px 9px; border-radius: 8px; }}
    QListWidget::item:selected {{ background: {p['card']}; color: {ink}; }}
    QListWidget::item:hover {{ background: {p['card']}; }}
    QProgressBar {{ border: none; background: {p['card']}; border-radius: 3px; min-height: 5px; max-height: 5px; }}
    QProgressBar::chunk {{ background: {a}; border-radius: 3px; }}
    QCheckBox {{ spacing: 10px; padding: 8px 0px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {p['muted']}; border-radius: 5px; }}
    QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}
    QSlider::groove:horizontal {{ height: 5px; background: {p['line']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 16px; margin: -5px 0px; background: {a}; border-radius: 8px; }}
    QMenu {{ background: {p['panel']}; border: 1px solid {p['line']}; padding: 5px; }}
    QMenu::item {{ padding: 7px 18px; }}
    QMenu::item:selected {{ background: {p['card']}; color: {a}; }}
    QStatusBar {{ background: {p['panel']}; color: {p['muted']}; font-size: 11px; }}
    QScrollBar:vertical {{ width: 8px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {p['line']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    """
