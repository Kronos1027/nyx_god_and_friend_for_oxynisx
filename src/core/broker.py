"""Resident model registry with real unloads and VRAM admission.

An earlier revision tracked model handles but never released anything: ``release``
only forgot the handle, so eviction could not actually free memory. Every handle
now carries an optional unload callback that runs on release and eviction, and
the VRAM reading comes from the same ``runtime_budget`` snapshot used elsewhere.
Ollama keeps governing its own models; this registry covers models Nyx loads
inside its process, such as speech recognition.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

MIB = 1024 * 1024


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
    unload: Optional[Callable[[], None]] = None


class ModelBroker:
    """Central registry of optional resident models for this process."""

    BUDGET_MB: int = 11_000  # 12 GB minus headroom for Windows DWM
    HYSTERESIS_SECONDS: float = 20.0

    _instance: Optional["ModelBroker"] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ModelBroker":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, budget_mb: int = BUDGET_MB) -> None:
        self.budget_mb = budget_mb
        self.active_models: Dict[ModelRole, ModelHandle] = {}
        self.swap_count = 0
        self.unload_failures = 0
        self.peak_vram_mb = 0
        self._lock = threading.RLock()

    # -- telemetry ---------------------------------------------------------
    def current_vram_used_mb(self) -> int:
        """Read real VRAM usage, preferring the shared resource snapshot."""
        try:
            from core.runtime_budget import resource_snapshot

            snapshot = resource_snapshot()
            if snapshot.vram_total_bytes is not None and snapshot.vram_free_bytes is not None:
                used = max(0, (snapshot.vram_total_bytes - snapshot.vram_free_bytes) // MIB)
                self.peak_vram_mb = max(self.peak_vram_mb, used)
                return used
        except Exception:
            log.debug("VRAM snapshot unavailable for the broker", exc_info=True)
        # Unknown telemetry must stay conservative rather than report zero use.
        return min(self.budget_mb, 3_500)

    def pressure(self) -> float:
        """0.0 = free, 1.0 = at the configured budget."""
        return min(1.0, self.current_vram_used_mb() / float(self.budget_mb))

    # -- lifecycle ---------------------------------------------------------
    def acquire(
        self,
        role: ModelRole,
        model_name: str,
        estimated_mb: int,
        ttl: int = 300,
        unload: Callable[[], None] | None = None,
    ) -> ModelHandle:
        """Register a resident model, evicting idle lower-priority roles if needed."""
        now = time.time()
        with self._lock:
            if role in self.active_models:
                handle = self.active_models[role]
                handle.last_used = now
                handle.model_name = model_name
                handle.estimated_mb = estimated_mb
                if unload is not None:
                    handle.unload = unload
                return handle

            free_mb = self.budget_mb - self.current_vram_used_mb()
            if estimated_mb > free_mb:
                self._evict_to_fit(estimated_mb)

            handle = ModelHandle(
                role=role,
                model_name=model_name,
                loaded_at=now,
                last_used=now,
                estimated_mb=estimated_mb,
                ttl_seconds=ttl,
                unload=unload,
            )
            self.active_models[role] = handle
        log.info("ModelBroker: %s residente (%s, ~%d MB)", model_name, role.value, estimated_mb)
        return handle

    def touch(self, role: ModelRole) -> None:
        """Mark a resident model as recently used so idle eviction spares it."""
        with self._lock:
            if handle := self.active_models.get(role):
                handle.last_used = time.time()

    def release(self, role: ModelRole) -> bool:
        """Unload one role for real; returns True when a model was registered."""
        with self._lock:
            handle = self.active_models.pop(role, None)
        if handle is None:
            return False
        self.swap_count += 1
        self._run_unload(handle)
        log.info("ModelBroker: liberado %s do papel %s", handle.model_name, role.value)
        return True

    def release_idle(self, older_than_seconds: float | None = None) -> list[str]:
        """Release every model unused for longer than its TTL (or the given age)."""
        now = time.time()
        with self._lock:
            stale = [
                role for role, handle in self.active_models.items()
                if now - handle.last_used >= (older_than_seconds if older_than_seconds is not None else handle.ttl_seconds)
            ]
        released = []
        for role in stale:
            if self.release(role):
                released.append(role.value)
        return released

    def _run_unload(self, handle: ModelHandle) -> None:
        if handle.unload is None:
            return
        try:
            handle.unload()
        except Exception:
            self.unload_failures += 1
            log.warning("ModelBroker: falha ao descarregar %s", handle.model_name, exc_info=True)

    def _evict_to_fit(self, needed_mb: int) -> None:
        """Release idle models from the least important role upwards."""
        priority = [ModelRole.EMBEDDINGS, ModelRole.TTS, ModelRole.STT, ModelRole.GROUNDER]
        for role in priority:
            if (self.budget_mb - self.current_vram_used_mb()) >= needed_mb:
                break
            handle = self.active_models.get(role)
            if handle is None:
                continue
            if (time.time() - handle.last_used) < self.HYSTERESIS_SECONDS:
                log.info("ModelBroker: %s em uso recente; não despejado", role.value)
                continue
            log.warning("ModelBroker: despejando %s para liberar %d MB", handle.model_name, needed_mb)
            self.release(role)

    # -- reporting ---------------------------------------------------------
    def get_telemetry(self) -> Dict[str, Any]:
        used = self.current_vram_used_mb()
        with self._lock:
            roles = [role.value for role in self.active_models]
            resident = [handle.model_name for handle in self.active_models.values()]
        return {
            "vram_used_mb": used,
            "vram_budget_mb": self.budget_mb,
            "pressure": round(self.pressure(), 3),
            "peak_vram_mb": self.peak_vram_mb,
            "swap_count": self.swap_count,
            "unload_failures": self.unload_failures,
            "active_roles": roles,
            "resident": resident,
        }
