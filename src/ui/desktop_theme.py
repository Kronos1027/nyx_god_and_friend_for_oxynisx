"""Compatibility entry point for the token-generated Nyx HUD theme."""
from ui.hud.theme import stylesheet
from ui.tokens import hud_palette

PALETTES = {name:hud_palette(name) for name in ('midnight','daylight')}
ACCENTS = {'gold':hud_palette()['gold'], 'teal':hud_palette()['teal']}
# Existing preferences migrate to the closest HUD semantic, without old colors.
ACCENTS.update(violet=ACCENTS['gold'], amber=ACCENTS['gold'], cyan=ACCENTS['teal'], mint=ACCENTS['teal'])


def desktop_stylesheet(theme='midnight', accent='gold', font_size=14):
    return stylesheet(theme, accent, font_size)
