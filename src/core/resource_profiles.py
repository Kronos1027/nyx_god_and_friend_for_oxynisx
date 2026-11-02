"""Explicit resource profiles; no model switching or process observation."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

GIB = 1024 ** 3
# Cold starts succeeded from >=5.21 GiB free on this Windows PC. Round upward
# for automatic cold admission; this is an observed range, NOT a true minimum.
NORMAL_COLD_START_AVAILABLE_BYTES = int(5.3 * GIB)


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
    'conservative': ResourceProfile('Conservador', 4096, 4 * GIB, 0, 0, '5m'),
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


def default_profile(snapshot):
    """Choose startup defaults from measured headroom; keep manual overrides."""
    normal = PROFILES['normal']
    if (snapshot.ram_available_bytes is not None
            and snapshot.ram_available_bytes >= NORMAL_COLD_START_AVAILABLE_BYTES
            and snapshot.vram_free_bytes is not None
            and snapshot.vram_free_bytes >= normal.vram_reserve_bytes + normal.kv_reserve_bytes + 4 * GIB):
        return 'normal', 'Normal automático: recursos na faixa de carga fria observada neste PC.'
    return 'conservative', ('Conservador automático: RAM/VRAM fora da faixa de carga fria validada para Normal '
                            'ou telemetria indisponível. O modelo será limitado pelo orçamento atual.')


@contextmanager
def resource_profile_scope(name):
    if name not in PROFILES:
        raise ValueError('Perfil de recursos desconhecido.')
    token = _override.set(name)
    try:
        yield
    finally:
        _override.reset(token)
