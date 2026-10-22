"""Bounded inference admission and conservative RAM/VRAM budgeting."""

from __future__ import annotations

import logging
import json
import subprocess
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)
MIB = 1024 * 1024
GIB = 1024 * MIB


class InferenceBusyError(RuntimeError):
    """Nyx's bounded local-model queue is full or has waited too long."""


class InferencePressureError(RuntimeError):
    """The machine is under memory pressure; defer this model request."""


@dataclass(frozen=True)
class ResourceSnapshot:
    ram_available_bytes: int | None
    vram_total_bytes: int | None
    vram_free_bytes: int | None


def resource_snapshot() -> ResourceSnapshot:
    ram_available = None
    try:
        import psutil

        ram_available = int(psutil.virtual_memory().available)
    except Exception:
        log.debug("RAM telemetry unavailable", exc_info=True)

    vram_total = vram_free = None
    try:
        result = subprocess.run(
            [
                "nvidia-smi", "--query-gpu=memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            first_gpu = result.stdout.strip().splitlines()[0].split(",")
            vram_total, vram_free = (int(value.strip()) * MIB for value in first_gpu[:2])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        log.debug("NVIDIA VRAM telemetry unavailable")

    return ResourceSnapshot(ram_available, vram_total, vram_free)


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
                and size > 0 and gpu == size and 512 <= context <= safe_context_tokens(snapshot)):
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

    with INFERENCE_GATE.slot(timeout=max(timeout, 90.0)):
        snapshot = _free_then_snapshot(resource_snapshot())
        ensure_resource_headroom(snapshot)
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
        with urllib.request.urlopen(request, timeout=max(timeout, 120.0)) as response:
            return json.loads(response.read().decode("utf-8"))


class InferenceGate:
    """One active generation plus a small FIFO, shared by every Nyx caller."""

    def __init__(self, max_waiters: int = 2) -> None:
        self.max_waiters = max_waiters
        self._condition = threading.Condition()
        self._queue: deque[object] = deque()
        self._active = False

    def telemetry(self) -> dict[str, int]:
        with self._condition:
            return {"active": int(self._active), "waiting": len(self._queue), "max_waiters": self.max_waiters}

    @contextmanager
    def slot(self, timeout: float = 45.0) -> Iterator[None]:
        ticket = object()
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            if not self._active and not self._queue:
                self._active = True
            else:
                if len(self._queue) >= self.max_waiters:
                    raise InferenceBusyError("A fila local de inferência está cheia; tente novamente em instantes.")
                self._queue.append(ticket)
                while self._active or not self._queue or self._queue[0] is not ticket:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._queue.remove(ticket)
                        self._condition.notify_all()
                        raise InferenceBusyError("A solicitação aguardou demais na fila local e foi cancelada.")
                    self._condition.wait(remaining)
                if time.monotonic() >= deadline:
                    self._queue.remove(ticket)
                    self._condition.notify_all()
                    raise InferenceBusyError("A solicitação aguardou demais na fila local e foi cancelada.")
                self._queue.popleft()
                self._active = True
        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()


INFERENCE_GATE = InferenceGate(max_waiters=2)
