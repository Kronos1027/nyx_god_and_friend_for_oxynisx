"""Bounded inference admission and conservative RAM/VRAM budgeting."""

from __future__ import annotations

import logging
import json
import subprocess
import threading
import time
import sys
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)
MIB = 1024 * 1024
GIB = 1024 * MIB


class InferenceBusyError(RuntimeError):
    """Nyx's bounded local-model queue is full or has waited too long."""


class InferencePressureError(RuntimeError):
    """The machine is under memory pressure; defer this model request."""


class InferenceCancelledError(InferenceBusyError):
    """A waiting request was cancelled before it acquired resources."""


class WorkPriority(IntEnum):
    EMERGENCY = 0
    INTERACTIVE = 1
    VOICE = 2
    TASK = 3
    SUGGESTION = 4
    BACKGROUND = 5


_work_context = ContextVar("nyx_work", default=(WorkPriority.INTERACTIVE, None))


@contextmanager
def inference_scope(priority=WorkPriority.INTERACTIVE, cancelled=None):
    """Propagate scheduling intent through local synchronous model wrappers."""
    token = _work_context.set((WorkPriority(priority), cancelled))
    try:
        yield
    finally:
        _work_context.reset(token)


@dataclass(frozen=True)
class ResourceSnapshot:
    ram_available_bytes: int | None
    vram_total_bytes: int | None
    vram_free_bytes: int | None
    cpu_percent: float | None = None
    ram_total_bytes: int | None = None
    committed_bytes: int | None = None
    commit_limit_bytes: int | None = None


def windows_commit_memory() -> tuple[int | None, int | None]:
    """GetPerformanceInfo reports committed pages, not physical RAM usage."""
    if sys.platform != "win32":
        return None, None
    try:
        import ctypes
        from ctypes import wintypes
        class PerformanceInformation(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable",
                    "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize",
                )
            ] + [(name, wintypes.DWORD) for name in ("HandleCount", "ProcessCount", "ThreadCount")]
        data = PerformanceInformation()
        data.cb = ctypes.sizeof(data)
        query = ctypes.WinDLL("psapi", use_last_error=True).GetPerformanceInfo
        query.argtypes = [ctypes.POINTER(PerformanceInformation), wintypes.DWORD]
        query.restype = wintypes.BOOL
        if query(ctypes.byref(data), data.cb):
            return data.CommitTotal * data.PageSize, data.CommitLimit * data.PageSize
    except (OSError, AttributeError):
        log.debug("Windows commit telemetry unavailable", exc_info=True)
    return None, None


_nvml_lock = threading.Lock()
_nvml = None
_nvml_handle = None
_nvml_retry_at = 0.0


def _gpu_memory() -> tuple[int | None, int | None]:
    """Fresh NVML readings without starting a process for every request."""
    global _nvml, _nvml_handle, _nvml_retry_at
    with _nvml_lock:
        try:
            if _nvml is None and time.monotonic() >= _nvml_retry_at:
                import pynvml
                pynvml.nvmlInit()
                _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                _nvml = pynvml
            if _nvml is not None:
                memory = _nvml.nvmlDeviceGetMemoryInfo(_nvml_handle)
                return int(memory.total), int(memory.free)
        except Exception:
            _nvml = _nvml_handle = None
            _nvml_retry_at = time.monotonic() + 30
    return _gpu_memory_subprocess()


def _gpu_memory_subprocess() -> tuple[int | None, int | None]:
    """Compatibility fallback when NVML is absent or unavailable."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1.5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            total, free = result.stdout.strip().splitlines()[0].split(",")[:2]
            return int(total.strip()) * MIB, int(free.strip()) * MIB
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        log.debug("NVIDIA VRAM telemetry unavailable")
    return None, None


def resource_snapshot() -> ResourceSnapshot:
    ram_available = ram_total = cpu = None
    try:
        import psutil

        memory = psutil.virtual_memory()
        ram_available, ram_total = int(memory.available), int(memory.total)
        cpu = psutil.cpu_percent(interval=None)
    except Exception:
        log.debug("RAM telemetry unavailable", exc_info=True)

    vram_total, vram_free = _gpu_memory()
    committed, limit = windows_commit_memory()
    return ResourceSnapshot(ram_available, vram_total, vram_free, cpu, ram_total, committed, limit)


def model_weight_budget_bytes(snapshot: ResourceSnapshot) -> int | None:
    """Estimate a safe maximum disk-sized model, leaving OS/display headroom."""
    ram_budget = (
        max(0, snapshot.ram_available_bytes - 2 * GIB)
        if snapshot.ram_available_bytes is not None
        else None
    )
    if snapshot.vram_free_bytes is not None:
        gpu_budget = max(0, snapshot.vram_free_bytes - 4 * GIB)
        if ram_budget is not None:
            if snapshot.ram_available_bytes >= 4 * GIB:
                return min(gpu_budget, ram_budget * 2)
            staging = max(0, snapshot.ram_available_bytes - 1 * GIB)
            return min(gpu_budget, staging * 3)
        return gpu_budget
    if ram_budget is None:
        return None
    # CPU-only model sizes are capped to avoid selecting a 12B+ model just
    # because a machine reports very large RAM.
    return min(ram_budget, 8 * GIB)


def admit_gguf_load(path: Path, requested_context: int) -> int:
    snapshot = _free_then_snapshot(resource_snapshot())
    ensure_resource_headroom(snapshot)
    # The bundled llama.cpp wheel may be CPU-only; require host capacity for
    # the full file even on computers with an NVIDIA card.
    budget = max(0, snapshot.ram_available_bytes - 2 * GIB) if snapshot.ram_available_bytes is not None else 4 * GIB
    if path.stat().st_size > budget:
        raise InferencePressureError(
            f"O GGUF {path.name} não cabe na memória livre com a reserva do sistema. Libere memória antes de carregá-lo."
        )
    return min(max(512, requested_context), safe_context_tokens(snapshot))


def safe_context_tokens(snapshot: ResourceSnapshot) -> int:
    """Choose a small context from current free memory; never exceed 4096."""
    ram = snapshot.ram_available_bytes
    if ram is not None and ram < 3 * GIB:
        return 1024
    if ram is not None and ram < 6 * GIB:
        return 2048
    free_vram = snapshot.vram_free_bytes
    if free_vram is not None:
        if free_vram < 2 * GIB:
            return 1024
        if free_vram < 5 * GIB:
            return 2048
    elif ram is not None and ram < 12 * GIB:
        return 2048
    return 4096


def ensure_resource_headroom(snapshot: ResourceSnapshot) -> None:
    if snapshot.ram_available_bytes is not None and snapshot.ram_available_bytes < 1 * GIB:
        raise InferencePressureError("RAM livre abaixo de 1 GiB; aguarde o sistema liberar memória.")
    if snapshot.vram_free_bytes is not None and snapshot.vram_free_bytes < 768 * MIB:
        raise InferencePressureError("VRAM livre abaixo de 768 MiB; aguarde antes de gerar.")


IDLE_RESIDENT_SECONDS = 60.0


def under_pressure(snapshot: ResourceSnapshot) -> bool:
    """True when optional resident models should give way to the main model."""
    if snapshot.ram_available_bytes is not None and snapshot.ram_available_bytes < 3 * GIB:
        return True
    return snapshot.vram_free_bytes is not None and snapshot.vram_free_bytes < 1536 * MIB


def _resident_idle_seconds(snapshot: ResourceSnapshot) -> float:
    """Critical pressure ignores the idle grace period."""
    if snapshot.ram_available_bytes is not None and snapshot.ram_available_bytes < 1536 * MIB:
        return 0.0
    if snapshot.vram_free_bytes is not None and snapshot.vram_free_bytes < 1024 * MIB:
        return 0.0
    return IDLE_RESIDENT_SECONDS


def release_idle_residents(snapshot: ResourceSnapshot) -> list[str]:
    """Unload optional in-process models (speech, embeddings) under pressure.

    Freeing memory must never fail the inference that asked for room, so errors
    are logged and an empty list is returned.
    """
    if not under_pressure(snapshot):
        return []
    try:
        from core.broker import ModelBroker

        return ModelBroker.get_instance().release_idle(_resident_idle_seconds(snapshot))
    except Exception:
        log.debug("Resident model release failed", exc_info=True)
        return []


def _free_then_snapshot(snapshot: ResourceSnapshot) -> ResourceSnapshot:
    """Give resident models a chance to unload, then re-read real memory."""
    if not release_idle_residents(snapshot):
        return snapshot
    fresh = resource_snapshot()
    ensure_resource_headroom(fresh)
    return fresh


def ollama_models(host: str, endpoint: str) -> list[dict]:
    """Read a bounded, fresh inventory; unknown telemetry never grants residency."""
    import urllib.request

    for attempt in range(2):
        try:
            with urllib.request.urlopen(f"{host}/api/{endpoint}", timeout=5.0) as response:
                raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                return []
            data = json.loads(raw)
            models = data.get("models", [])
            return [item for item in models if isinstance(item, dict)] if isinstance(models, list) else []
        except (OSError, ValueError, AttributeError):
            if attempt == 0:
                time.sleep(0.3)
                continue
            return []
    return []


def resident_context(snapshot: ResourceSnapshot, installed: dict, running: list[dict]) -> int | None:
    """Reuse only the exact fully GPU-resident model without growing its context."""
    if (snapshot.ram_available_bytes is None or snapshot.ram_available_bytes <= 1 * GIB
            or snapshot.vram_free_bytes is None or snapshot.vram_free_bytes < 4 * GIB):
        return None
    digest = installed.get("digest")
    if not isinstance(digest, str) or not digest:
        return None
    for model in running:
        if model.get("name") != installed.get("name") or model.get("digest") != digest:
            continue
        size, gpu, context = (model.get(key) for key in ("size", "size_vram", "context_length"))
        if (all(type(value) is int for value in (size, gpu, context))
                and size > 0 and gpu == size and 512 <= context <= 4096):
            # Already allocated context is not a new allocation. Fluctuation
            # below the cold-load RAM threshold must not discard residency.
            return context
    return None


def ollama_request_context(host: str, model: str, snapshot: ResourceSnapshot) -> int:
    """Recheck admission inside the inference queue, including expired residents."""
    installed = next((item for item in ollama_models(host, "tags") if item.get("name") == model), {})
    context = resident_context(snapshot, installed, ollama_models(host, "ps"))
    if context is not None:
        return context
    size = installed.get("size")
    budget = model_weight_budget_bytes(snapshot)
    if budget is None:
        budget = 4 * GIB
    if type(size) is not int or not 0 < size <= budget:
        raise InferencePressureError("O modelo não cabe no orçamento atual ou seu tamanho não pôde ser confirmado. Libere memória e tente novamente.")
    return safe_context_tokens(snapshot)


def post_ollama_json(url: str, payload: dict, timeout: float) -> dict:
    """Send one serialized Ollama inference request under the shared budget."""
    import urllib.request

    from core.resource_governor import RESOURCE_GOVERNOR
    deadline = time.monotonic() + timeout
    priority, cancelled = _work_context.get()
    with INFERENCE_GATE.slot(timeout=timeout, priority=priority, cancelled=cancelled):
        snapshot = _free_then_snapshot(resource_snapshot())
        ensure_resource_headroom(snapshot)
        RESOURCE_GOVERNOR.admit(snapshot, priority)
        request_payload = dict(payload)
        if url.endswith("/api/chat") or url.endswith("/api/generate"):
            options = dict(request_payload.get("options", {}))
            host = url.rsplit("/api/", 1)[0]
            options["num_ctx"] = ollama_request_context(host, request_payload.get("model", ""), snapshot)
            request_payload["options"] = options
        request = urllib.request.Request(
            url,
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if cancelled is not None and cancelled():
            raise InferenceCancelledError("Pedido cancelado antes da inferência.")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InferenceBusyError("Prazo esgotado antes de enviar a inferência.")
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=remaining) as response:
                raw = response.read(2_097_153)
                if len(raw) > 2_097_152:
                    raise ValueError("Resposta do modelo excedeu 2 MiB")
                return json.loads(raw.decode("utf-8"))
        finally:
            RESOURCE_GOVERNOR.record_latency(time.monotonic() - started)


class InferenceGate:
    """One generation; bounded priority queue, FIFO within each priority."""

    def __init__(self, max_waiters: int = 2) -> None:
        self.max_waiters = max_waiters
        self._condition = threading.Condition()
        self._queue: deque[object] = deque()
        self._active = False

    def telemetry(self) -> dict[str, int]:
        with self._condition:
            return {"active": int(self._active), "waiting": len(self._queue), "max_waiters": self.max_waiters}

    @contextmanager
    def slot(self, timeout: float = 45.0, *, priority=WorkPriority.INTERACTIVE, cancelled=None) -> Iterator[None]:
        priority = WorkPriority(priority)
        ticket = object()
        entry = (priority, ticket)
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            if cancelled is not None and cancelled():
                raise InferenceCancelledError("Pedido cancelado antes de entrar na fila.")
            if not self._active and not self._queue:
                self._active = True
            else:
                capacity = self.max_waiters
                if priority >= WorkPriority.SUGGESTION:
                    capacity = max(0, capacity - 1)  # reserve a waiting place for the user
                if len(self._queue) >= capacity:
                    raise InferenceBusyError("A fila local de inferência está cheia; tente novamente em instantes.")
                self._queue.append(entry)
                self._queue = deque(sorted(self._queue, key=lambda item: item[0]))
                try:
                    while True:
                        if cancelled is not None and cancelled():
                            raise InferenceCancelledError("Pedido cancelado enquanto aguardava inferência.")
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise InferenceBusyError("A solicitação aguardou demais na fila local e foi cancelada.")
                        if not self._active and self._queue[0][1] is ticket:
                            break
                        self._condition.wait(min(remaining, 0.1) if cancelled else remaining)
                except BaseException:
                    self._queue.remove(entry)
                    self._condition.notify_all()
                    raise
                self._queue.popleft()
                self._active = True
        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()


INFERENCE_GATE = InferenceGate(max_waiters=2)
