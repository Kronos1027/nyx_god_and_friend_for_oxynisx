"""Resource admission for optional work; no polling thread or model generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
import math
from pathlib import Path
import threading

from core.runtime_budget import GIB, MIB, ResourceSnapshot, WorkPriority, InferencePressureError


class OperatingMode(str, Enum):
    SLEEP = "sleep"
    IDLE = "idle"
    CONVERSATION = "conversation"
    WORKING = "working"
    CREATIVE = "creative"
    PRESSURE = "pressure"


@dataclass(frozen=True)
class ResourcePolicy:
    ram_reserve_bytes: int = GIB
    vram_reserve_bytes: int = 768 * MIB
    background_ram_bytes: int = 3 * GIB
    background_cpu_percent: float = 85
    background_latency_seconds: float = 30

    def __post_init__(self):
        for name in ("ram_reserve_bytes", "vram_reserve_bytes", "background_ram_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < MIB:
                raise ValueError(f"{name} deve ser um inteiro positivo em bytes (mínimo 1 MiB)")
        if self.ram_reserve_bytes < GIB or self.vram_reserve_bytes < 768 * MIB:
            raise ValueError("As reservas mínimas são 1 GiB de RAM e 768 MiB de VRAM")
        if self.background_ram_bytes < self.ram_reserve_bytes:
            raise ValueError("Trabalho de fundo precisa respeitar a reserva de RAM")
        for value in (self.background_cpu_percent, self.background_latency_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("Limites de CPU e latência devem ser positivos e finitos")
        if self.background_cpu_percent > 100:
            raise ValueError("Limite de CPU deve ser menor ou igual a 100")


@dataclass(frozen=True)
class ResourceDecision:
    allowed: bool
    mode: OperatingMode
    reason: str


class ResourceGovernor:
    def __init__(self, policy=None):
        self._lock = threading.RLock()
        self.policy = policy or ResourcePolicy()
        self.mode = OperatingMode.IDLE
        self._requested_mode = OperatingMode.IDLE
        self.focused = False
        self.latency_seconds = None
        self.completed = 0
        self.denied = 0
        self.last_reason = ""
        self.last_snapshot = None

    def configure(self, policy: ResourcePolicy):
        if not isinstance(policy, ResourcePolicy):
            raise ValueError("Política de recursos inválida")
        with self._lock:
            self.policy = policy

    def set_mode(self, mode: OperatingMode | str, *, focused=False):
        mode = OperatingMode(mode)
        if mode == OperatingMode.PRESSURE:
            raise ValueError("Pressure é definido pela telemetria")
        with self._lock:
            self._requested_mode = mode
            self.focused = bool(focused)

    def evaluate(self, snapshot: ResourceSnapshot, priority=WorkPriority.INTERACTIVE, *, queued=0):
        priority = WorkPriority(priority)
        with self._lock:
            policy = self.policy
            self.last_snapshot = snapshot
            critical = (
                snapshot.ram_available_bytes is not None and snapshot.ram_available_bytes < policy.ram_reserve_bytes
            ) or (snapshot.vram_free_bytes is not None and snapshot.vram_free_bytes < policy.vram_reserve_bytes)
            if snapshot.committed_bytes is not None and snapshot.commit_limit_bytes is not None:
                critical = critical or snapshot.commit_limit_bytes - snapshot.committed_bytes < policy.ram_reserve_bytes
            self.mode = OperatingMode.PRESSURE if critical else self._requested_mode
            reason = ""
            if critical:
                reason = "Reserva de RAM/VRAM atingida; novas inferências adiadas."
            elif self.mode == OperatingMode.SLEEP:
                reason = "Modo sono: inferência suspensa até uma interação do usuário."
            elif priority >= WorkPriority.SUGGESTION:
                if self.focused or self.mode in {OperatingMode.CONVERSATION, OperatingMode.WORKING, OperatingMode.CREATIVE}:
                    reason = "Trabalho de fundo adiado durante foco ou tarefa interativa."
                elif snapshot.ram_available_bytes is None or snapshot.cpu_percent is None:
                    reason = "Telemetria incompleta; trabalho opcional adiado."
                elif snapshot.ram_available_bytes < policy.background_ram_bytes:
                    reason = "RAM reservada para o usuário; trabalho de fundo adiado."
                elif snapshot.cpu_percent >= policy.background_cpu_percent or queued:
                    reason = "CPU ou fila ocupada; trabalho de fundo adiado."
                elif self.latency_seconds is not None and self.latency_seconds > policy.background_latency_seconds:
                    reason = "Latência elevada; trabalho de fundo adiado."
            self.last_reason = reason
            if reason:
                self.denied += 1
            return ResourceDecision(not reason, self.mode, reason)

    def admit(self, snapshot, priority):
        decision = self.evaluate(snapshot, priority)
        if not decision.allowed:
            raise InferencePressureError(decision.reason)

    def record_latency(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            return
        with self._lock:
            self.latency_seconds = seconds if self.latency_seconds is None else 0.25 * seconds + 0.75 * self.latency_seconds
            self.completed += 1

    def telemetry(self):
        with self._lock:
            return {"mode": self.mode.value, "focused": self.focused, "completed": self.completed,
                    "denied": self.denied, "latency_seconds": self.latency_seconds,
                    "reason": self.last_reason, "policy": asdict(self.policy),
                    "resources": asdict(self.last_snapshot) if self.last_snapshot else None}

    def save_policy(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self.policy), indent=2), encoding="utf-8")
        temporary.replace(path)

    def load_policy(self, path: Path):
        path = Path(path)
        if path.stat().st_size > 8192:
            raise ValueError("Configuração de recursos excede o limite")
        self.configure(ResourcePolicy(**json.loads(path.read_text(encoding="utf-8"))))


RESOURCE_GOVERNOR = ResourceGovernor()
