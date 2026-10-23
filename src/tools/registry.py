"""Nyx — tools/registry.py

Registro central de ferramentas do agente. O agent_loop NUNCA executa
nada diretamente: sempre via registry, para que toda ação passe pelas
mesmas checagens de segurança e pela mesma auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    error: str | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class ToolSpec:
    """Metadados de segurança de uma ferramenta.

    destructive : ação destrutiva -> SEMPRE pede confirmação, mesmo em
                  modo autônomo (seção 4.2 — sem exceção).
    sensitive   : em modo assistido, pede confirmação.
    destructive_probe : para ferramentas cujo flag destrutivo depende dos
                  params (ex.: 'shell', onde o template DELETE_FILE é
                  destrutivo e LIST_DIR não) — recebe os params da ação e
                  responde se ESTE pedido específico é destrutivo.
    sensitive_probe : mesma ideia para confirmação em modo assistido, quando
                  só algumas ações tocam o mundo (ex.: 'browser' onde ler é
                  livre e clicar/digitar pedem confirmação).
    """

    name: str
    description: str
    destructive: bool = False
    sensitive: bool = False
    destructive_probe: Callable[[dict], bool] | None = None
    sensitive_probe: Callable[[dict], bool] | None = None
    input_contract: dict | list | None = None

    def is_destructive_for(self, params: dict) -> bool:
        """Veredicto destrutivo para um pedido concreto (type + params)."""
        if self.destructive:
            return True
        if self.destructive_probe is not None:
            try:
                return bool(self.destructive_probe(params or {}))
            except Exception:  # noqa: BLE001 — fail-safe: dúvida = destrutivo
                return True
        return False

    def is_sensitive_for(self, params: dict) -> bool:
        """Confirmação em modo assistido, possivelmente por tipo de ação."""
        if self.sensitive:
            return True
        if self.sensitive_probe is not None:
            try:
                return bool(self.sensitive_probe(params or {}))
            except Exception:  # noqa: BLE001 — fail-safe: dúvida = pede confirmação
                return True
        return False


ToolFunc = Callable[[dict], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, ToolFunc]] = {}
        from core.operation_control import OperationControl
        self.control = OperationControl()
        from threading import Lock
        self.team_run_lock = Lock()
        self.team_inference_lock = Lock()
        self.team_outstanding = []
        self.disabled_tools: set[str] = set()

    def register(self, spec: ToolSpec, func: ToolFunc) -> None:
        if spec.name in self._tools:
            raise ValueError(f"ferramenta duplicada: {spec.name}")
        self._tools[spec.name] = (spec, func)

    def get(self, name: str) -> tuple[ToolSpec, ToolFunc] | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def available_tools(self) -> list[str]:
        return self.names()

    def spec(self, name: str) -> ToolSpec | None:
        entry = self._tools.get(name)
        return entry[0] if entry else None

    def execute(self, name: str, params: dict) -> ToolResult:
        """Executa ferramenta registrada. Ferramenta desconhecida = erro,
        nunca exceção estourando (o loop audita o resultado)."""
        if name in self.disabled_tools:
            return ToolResult(False, error="Ferramenta desabilitada no runtime.",
                              meta={"blocked": True, "reason": "disabled_tool"})
        if self.control.is_cancelled():
            return ToolResult(False, error="Ferramentas interrompidas; confira a atividade antes de retomar.",
                              meta={"blocked": True, "reason": "cancelled"})
        entry = self._tools.get(name)
        if entry is None:
            return ToolResult(
                ok=False,
                error=f"ferramenta desconhecida: {name!r}",
                meta={"blocked": True, "reason": "unknown_tool"},
            )
        spec, func = entry
        try:
            return func(dict(params or {}))
        except Exception as exc:  # noqa: BLE001 — barreira de isolamento por ferramenta
            return ToolResult(
                ok=False,
                error=f"exceção em {name}: {type(exc).__name__}: {exc}",
                meta={"tool": name},
            )
