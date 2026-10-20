"""Nyx AGI Desktop v3 — core/broker.py (Model Broker de VRAM para RTX 3060)

Orquestra alocação e desalocação dinâmica de modelos (Planner, Grounder, STT, TTS)
com medição empírica de VRAM via NVML, histerese anti-thrashing e teto de 11.000 MB.
"""

from __future__ import annotations

import logging
import time
import warnings as _w
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

HAS_NVML = False
NVML_HANDLE = None

try:
    # Suprime FutureWarning do pynvml durante o import (o aviso é emitido
    # dentro de pynvml/__init__.py ao carregar — catch_warnings é a única
    # forma confiável de interceptá-lo antes que chegue ao pytest/logging)
    with _w.catch_warnings():
        _w.filterwarnings("ignore", category=FutureWarning)
        import pynvml  # pynvml namespace do nvidia-ml-py

    pynvml.nvmlInit()
    HAS_NVML = True
    NVML_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    pass


class ModelRole(str, Enum):
    PLANNER = "planner"
    GROUNDER = "grounder"
    STT = "stt"
    TTS = "tts"
    EMBEDDINGS = "embeddings"


@dataclass
class ModelHandle:
    role: ModelRole
    model_name: str
    loaded_at: float
    last_used: float
    estimated_mb: int
    ttl_seconds: int = 300


class ModelBroker:
    """Gerenciador central de orçamento de VRAM da GPU."""

    BUDGET_MB: int = 11_000  # 12GB - 1.28GB de margem para o Windows 11 DWM
    HYSTERESIS_SECONDS: float = 20.0

    _instance: Optional[ModelBroker] = None

    @classmethod
    def get_instance(cls) -> ModelBroker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, budget_mb: int = BUDGET_MB) -> None:
        self.budget_mb = budget_mb
        self.active_models: Dict[ModelRole, ModelHandle] = {}
        self.swap_count = 0
        self.peak_vram_mb = 0

    def current_vram_used_mb(self) -> int:
        """Lê o uso real e instantâneo de VRAM na GPU física via NVML."""
        if not HAS_NVML or not NVML_HANDLE:
            return 3500
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(NVML_HANDLE)
            used = int(mem.used // (1024 * 1024))
            if used > self.peak_vram_mb:
                self.peak_vram_mb = used
            return used
        except Exception:
            return 3500

    def pressure(self) -> float:
        """Calcula a pressão de VRAM (0.0 = livre, 1.0 = no limite do orçamento)."""
        used = self.current_vram_used_mb()
        return min(1.0, used / float(self.budget_mb))

    def acquire(self, role: ModelRole, model_name: str, estimated_mb: int, ttl: int = 300) -> ModelHandle:
        """Solicita o carregamento de um modelo, desalocando modelos com TTL expirado se necessário."""
        now = time.time()

        # Se já estiver ativo, atualiza last_used e retorna
        if role in self.active_models:
            handle = self.active_models[role]
            handle.last_used = now
            return handle

        # Checa se há espaço suficiente dentro do orçamento
        current_used = self.current_vram_used_mb()
        if (current_used + estimated_mb) > self.budget_mb:
            self._evict_to_fit(estimated_mb)

        handle = ModelHandle(
            role=role,
            model_name=model_name,
            loaded_at=now,
            last_used=now,
            estimated_mb=estimated_mb,
            ttl_seconds=ttl,
        )
        self.active_models[role] = handle
        log.info("ModelBroker: alocado modelo %s para papel %s (~%d MB)", model_name, role.value, estimated_mb)
        return handle

    def release(self, role: ModelRole) -> None:
        """Libera o modelo associado ao papel."""
        if role in self.active_models:
            handle = self.active_models.pop(role)
            self.swap_count += 1
            log.info("ModelBroker: liberado modelo %s do papel %s", handle.model_name, role.value)

    def _evict_to_fit(self, needed_mb: int) -> None:
        """Desaloca modelos de menor prioridade respeitando a janela de histerese."""
        now = time.time()
        # Ordem de despejo (menor prioridade primeiro): embeddings -> tts -> stt -> grounder -> planner
        eviction_priority = [
            ModelRole.EMBEDDINGS,
            ModelRole.TTS,
            ModelRole.STT,
            ModelRole.GROUNDER,
        ]

        for r in eviction_priority:
            if r in self.active_models:
                handle = self.active_models[r]
                # Respeita histerese
                if (now - handle.last_used) >= self.HYSTERESIS_SECONDS:
                    log.warning("ModelBroker: Despejando %s para liberar %d MB", handle.model_name, needed_mb)
                    self.release(r)
                    if (self.current_vram_used_mb() + needed_mb) <= self.budget_mb:
                        break

    def get_telemetry(self) -> Dict[str, Any]:
        """Retorna telemetria operacional do broker."""
        used = self.current_vram_used_mb()
        return {
            "vram_used_mb": used,
            "vram_budget_mb": self.budget_mb,
            "pressure": round(self.pressure(), 3),
            "peak_vram_mb": self.peak_vram_mb,
            "swap_count": self.swap_count,
            "active_roles": [r.value for r in self.active_models.keys()],
        }
