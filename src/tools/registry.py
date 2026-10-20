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
    """

    name: str
    description: str
    destructive: bool = False
    sensitive: bool = False
    destructive_probe: Callable[[dict], bool] | None = None

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


ToolFunc = Callable[[dict], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, ToolFunc]] = {}

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
