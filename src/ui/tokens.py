"""Nyx — ui/tokens.py (Design Tokens e Temas da Interface Generativa)

Tokens de cores, tipografia, bordas, sombras e efeitos para os temas:
- Nyx Neon (HUD ciano/magenta, glow, estética cyberpunk)
- Anime Cyber (Roxo, rosa e teal neon de alta energia)
- Minimal (Dark slate limpo, monocromático e moderno)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    bg_color: str
    bg_card: str
    fg_color: str
    fg_muted: str
    accent_primary: str
    accent_secondary: str
    accent_glow: str
    border_color: str
    border_radius: int
    font_family: str
    font_size_base: int
    header_gradient: str
    card_gradient: str


THEMES: Dict[str, ThemeTokens] = {
    "nyx_neon": ThemeTokens(
        name="Nyx Neon",
        bg_color="#090D16",
        bg_card="#0F172A",
        fg_color="#00F0FF",
        fg_muted="#64748B",
        accent_primary="#00F0FF",
        accent_secondary="#FF007F",
        accent_glow="rgba(0, 240, 255, 0.4)",
        border_color="#00F0FF",
        border_radius=8,
        font_family="Consolas, 'Segoe UI', monospace",
        font_size_base=12,
        header_gradient="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #090D16, stop:1 #1E1035)",
        card_gradient="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0F172A, stop:1 #090D16)",
    ),
    "anime_cyber": ThemeTokens(
        name="Anime Cyber",
        bg_color="#120D24",
        bg_card="#1A1535",
        fg_color="#F8FAFC",
        fg_muted="#A78BFA",
        accent_primary="#EC4899",
        accent_secondary="#8B5CF6",
        accent_glow="rgba(236, 72, 153, 0.45)",
        border_color="#8B5CF6",
        border_radius=12,
        font_family="'Segoe UI', Roboto, sans-serif",
        font_size_base=12,
        header_gradient="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8B5CF6, stop:1 #EC4899)",
        card_gradient="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1A1535, stop:1 #120D24)",
    ),
    "minimal": ThemeTokens(
        name="Minimal",
        bg_color="#0F172A",
        bg_card="#1E293B",
        fg_color="#F8FAFC",
        fg_muted="#94A3B8",
        accent_primary="#10B981",
        accent_secondary="#3B82F6",
        accent_glow="rgba(16, 185, 129, 0.2)",
        border_color="#334155",
        border_radius=6,
        font_family="'Segoe UI', -apple-system, sans-serif",
        font_size_base=12,
        header_gradient="qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E293B, stop:1 #0F172A)",
        card_gradient="qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E293B, stop:1 #0F172A)",
    ),
}


def get_theme(theme_name: str | None = None) -> ThemeTokens:
    """Retorna os tokens do tema pelo nome, fallback para 'nyx_neon'."""
    key = str(theme_name or "nyx_neon").lower().replace(" ", "_").replace("-", "_")
    return THEMES.get(key, THEMES["nyx_neon"])


def generate_stylesheet(theme: ThemeTokens) -> str:
    """Gera a folha de estilo QSS para janelas generativas."""
    return f"""
    QWidget#GenerativeWindowRoot {{
        background-color: {theme.bg_color};
        color: {theme.fg_color};
        font-family: {theme.font_family};
        border: 1px solid {theme.border_color};
        border-radius: {theme.border_radius}px;
    }}
    QFrame#HeaderBar {{
        background: {theme.header_gradient};
        border-bottom: 1px solid {theme.border_color};
        border-top-left-radius: {theme.border_radius}px;
        border-top-right-radius: {theme.border_radius}px;
    }}
    QLabel#WindowTitle {{
        color: {theme.accent_primary};
        font-weight: bold;
        font-size: 13px;
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QWidget#ScrollContainer {{
        background: transparent;
    }}
    QFrame#CardComponent {{
        background: {theme.card_gradient};
        border: 1px solid {theme.border_color};
        border-radius: {theme.border_radius - 2}px;
        padding: 8px;
    }}
    QLabel#CompTitle {{
        color: {theme.accent_secondary};
        font-weight: bold;
        font-size: 11px;
    }}
    QLabel#CompText {{
        color: {theme.fg_color};
        font-size: {theme.font_size_base}px;
    }}
    QTextEdit, QPlainTextEdit {{
        background-color: {theme.bg_card};
        color: {theme.fg_color};
        border: 1px solid {theme.border_color};
        border-radius: 4px;
        font-family: Consolas, monospace;
        font-size: 11px;
    }}
    QProgressBar {{
        background-color: {theme.bg_card};
        border: 1px solid {theme.border_color};
        border-radius: 4px;
        text-align: center;
        color: {theme.fg_color};
        font-weight: bold;
    }}
    QProgressBar::chunk {{
        background-color: {theme.accent_primary};
        border-radius: 3px;
    }}
    QPushButton {{
        background-color: {theme.accent_primary};
        color: #000000;
        font-weight: bold;
        border-radius: 4px;
        padding: 6px 14px;
        border: none;
    }}
    QPushButton:hover {{
        background-color: {theme.accent_secondary};
        color: #FFFFFF;
    }}
    QTableWidget {{
        background-color: {theme.bg_card};
        color: {theme.fg_color};
        gridline-color: {theme.border_color};
        border: 1px solid {theme.border_color};
        border-radius: 4px;
    }}
    QHeaderView::section {{
        background-color: {theme.bg_color};
        color: {theme.accent_primary};
        padding: 4px;
        border: 1px solid {theme.border_color};
        font-weight: bold;
    }}
    """
