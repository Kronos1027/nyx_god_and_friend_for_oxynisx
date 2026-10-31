"""Explicit resource profiles; no model switching or process observation."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

GIB = 1024 ** 3


@dataclass(frozen=True)
class ResourceProfile:
    label: str
    context_tokens: int
    vram_reserve_bytes: int
    kv_reserve_bytes: int
    resident_cap_bytes: int
    keep_alive: str | int
    background: bool = True


PROFILES = {
    'conservative': ResourceProfile('Conservador (atual)', 4096, 4 * GIB, 0, 0, '5m'),
    'normal': ResourceProfile('Normal', 8192, int(2.5 * GIB), GIB, int(9.5 * GIB), '10m'),
    'game': ResourceProfile('Jogo / Live', 4096, 7 * GIB, GIB // 2, 5 * GIB, 0, False),
    'focus': ResourceProfile('Foco', 16384, int(2.5 * GIB), int(1.5 * GIB), int(9.5 * GIB), '15m'),
}
_selected = 'conservative'
_override = ContextVar('nyx_resource_profile', default=None)


def select_profile(name):
    global _selected
    if name not in PROFILES:
        raise ValueError('Perfil de recursos desconhecido.')
    _selected = name


def profile_name():
    return _override.get() or _selected


def current_profile():
    return PROFILES[profile_name()]


@contextmanager
def resource_profile_scope(name):
    if name not in PROFILES:
        raise ValueError('Perfil de recursos desconhecido.')
    token = _override.set(name)
    try:
        yield
    finally:
        _override.reset(token)
