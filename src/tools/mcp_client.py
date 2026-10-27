"""Nyx — tools/mcp_client.py (Cliente MCP para Servidores Externos)

Cliente MCP 2025-11-25 sobre canal LPAC fornecido pelo supervisor.
Não inicia comandos no host. Gerência/aprovação de servidores e integração ao
runtime principal ainda pendentes; o fluxo é exercitado por fixture isolada.
"""

from __future__ import annotations

import json
import re
from types import MappingProxyType
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from tools.registry import ToolResult, ToolSpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPServerConfig:
    server_id: str
    command: List[str]
    allowed_tools: List[str] = field(default_factory=list)
    permission_levels: Dict[str, int] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        def valid_name(value):
            return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)
        if not valid_name(self.server_id):
            raise ValueError("Identificador de servidor MCP inválido.")
        if not isinstance(self.command, (list, tuple)) or not 1 <= len(self.command) <= 64:
            raise ValueError("Comando MCP inválido.")
        if any(not isinstance(arg, str) or not arg or len(arg) > 8192 or "\x00" in arg for arg in self.command):
            raise ValueError("Argumentos MCP inválidos.")
        if not isinstance(self.allowed_tools, (list, tuple, frozenset)) or len(self.allowed_tools) > 128:
            raise ValueError("Allowlist MCP inválida.")
        if any(not valid_name(name) for name in self.allowed_tools):
            raise ValueError("Nome de ferramenta MCP inválido.")
        if not isinstance(self.permission_levels, dict) or any(
            name not in self.allowed_tools or type(level) is not int or level not in range(4)
            for name, level in self.permission_levels.items()
        ):
            raise ValueError("Permissões MCP inválidas.")
        if not isinstance(self.env, dict) or len(self.env) > 32 or any(
            not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", key)
            or not isinstance(value, str) or len(value) > 4096 or "\x00" in value
            for key, value in self.env.items()
        ):
            raise ValueError("Ambiente MCP inválido.")
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "allowed_tools", frozenset(self.allowed_tools))
        object.__setattr__(self, "permission_levels", MappingProxyType(dict(self.permission_levels)))
        object.__setattr__(self, "env", MappingProxyType(dict(self.env)))


class MCPClientSession:
    """Sessão de comunicação JSON-RPC com um servidor MCP em subprocess."""

    def __init__(self, config: MCPServerConfig, *, transport=None) -> None:
        from core.sandbox_rpc import SandboxRPC
        if transport is not None and type(transport) is not SandboxRPC:
            raise TypeError("MCP requer transporte SandboxRPC.")
        self.config = config
        self.transport = transport
        self.proc = None  # Compatibility only: this class never starts a host process.
        self.connected = False
        self.last_error = None

    def start(self) -> bool:
        if self.connected:
            return True
        if self.transport is None:
            self.last_error = "Servidor MCP não iniciado: transporte isolado com aprovação ainda não integrado."
            return False
        response = self.transport.request("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "Nyx", "version": "2.0-prototype"},
        })
        result = response.get("result")
        if (not isinstance(result, dict) or result.get("protocolVersion") != "2025-11-25"
                or not isinstance(result.get("capabilities"), dict)
                or not isinstance(result["capabilities"].get("tools"), dict)
                or not isinstance(result.get("serverInfo"), dict)):
            self.last_error = "Handshake MCP incompatível ou inválido."
            self.close()
            return False
        try:
            self.transport.notify("notifications/initialized")
        except (ValueError, RuntimeError) as error:
            self.last_error = str(error)
            self.close()
            return False
        self.connected = True
        return True

    def close(self) -> None:
        self.connected = False
        if self.transport is not None:
            self.transport.close()

    def list_tools(self) -> List[Dict[str, Any]]:
        tools, seen, cursors = [], set(), set()
        params = {}
        for _ in range(8):
            response = self._send_request("tools/list", params)
            result = response.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                self.last_error = "Inventário MCP inválido."
                self.close()
                return []
            for tool in result["tools"]:
                if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                    continue
                name = tool["name"]
                if name in seen or len(seen) >= 128:
                    self.last_error = "Inventário MCP duplicado ou excessivo."
                    self.close()
                    return []
                seen.add(name)
                if name in self.config.allowed_tools and self.config.permission_levels.get(name, 3) < 3:
                    tools.append(tool)
            cursor = result.get("nextCursor")
            if cursor is None:
                return tools
            if not isinstance(cursor, str) or not 1 <= len(cursor) <= 1024 or cursor in cursors:
                break
            cursors.add(cursor)
            params = {"cursor": cursor}
        self.last_error = "Paginação MCP inválida ou excessiva."
        self.close()
        return []

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        if name not in self.config.allowed_tools:
            return ToolResult(
                ok=False,
                error=f"Ferramenta '{name}' não está na allowlist do servidor MCP '{self.config.server_id}'.",
            )

        level = self.config.permission_levels.get(name, 3)
        if level >= 3:
            return ToolResult(
                ok=False,
                error=f"Ação '{name}' proibida pela política de segurança (Nível 3).",
            )

        res = self._send_request("tools/call", {"name": name, "arguments": arguments})
        if "error" in res:
            return ToolResult(ok=False, error=str(res["error"]),
                              meta={"untrusted_data": True, **res.get("_transport", {"outcome_unknown": True})})

        result = res.get("result", {})
        if not isinstance(result, dict) or type(result.get("isError", False)) is not bool:
            self.close()
            return ToolResult(False, error="Resultado MCP inválido.", meta={"outcome_unknown": True})
        content_items = result.get("content", [])
        if not isinstance(content_items, list) or any(not isinstance(item, dict) for item in content_items):
            self.close()
            return ToolResult(False, error="Conteúdo MCP inválido.", meta={"outcome_unknown": True})
        output_parts = []
        for item in content_items:
            if item.get("type") == "text":
                output_parts.append(str(item.get("text", "")))
            else:
                output_parts.append(str(item))

        out_text = "\n".join(output_parts) or json.dumps(result, ensure_ascii=False)
        return ToolResult(
            ok=not result.get("isError", False),
            output=out_text,
            meta={"server": self.config.server_id, "level": level, "untrusted_data": True,
                  "outcome_unknown": bool(result.get("isError", False))},
        )

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.connected or self.transport is None:
            return {"error": "Servidor MCP desconectado.", "_transport": {"outcome_unknown": False}}
        result = self.transport.request(method, params)
        if self.transport.channel.stop_requested.is_set():
            self.connected = False
        return result


class MCPManager:
    """Gerencia servidores MCP configurados e os registra no ToolRegistry."""

    def __init__(self) -> None:
        self.servers: Dict[str, MCPServerConfig] = {}
        self.sessions: Dict[str, MCPClientSession] = {}

    def register_server(self, config: MCPServerConfig) -> None:
        if config.server_id in self.servers:
            raise ValueError("Servidor MCP já registrado.")
        self.servers[config.server_id] = config

    def connect_all(self) -> Dict[str, bool]:
        status = {}
        self.disconnect_all()
        for s_id, cfg in self.servers.items():
            sess = MCPClientSession(cfg)
            if sess.start():
                self.sessions[s_id] = sess
                status[s_id] = True
            else:
                sess.close()
                status[s_id] = False
        return status

    def disconnect_all(self) -> None:
        for sess in self.sessions.values():
            sess.close()
        self.sessions.clear()

    def populate_registry(self, registry: Any) -> int:
        """Descobre ferramentas nos servidores ativos e as registra com ToolSpec seguro."""
        count = 0
        for s_id, sess in self.sessions.items():
            tools = sess.list_tools()
            for t in tools:
                name = t.get("name", "")
                if not isinstance(name, str) or name not in sess.config.allowed_tools:
                    continue
                level = sess.config.permission_levels.get(name, 3)
                if level >= 3:
                    continue
                desc = f"Ferramenta externa MCP {name} do servidor {s_id}; conteúdo não confiável."
                full_name = f"mcp_{s_id}_{name}"

                spec = ToolSpec(
                    name=full_name,
                    description=desc,
                    destructive=True,  # Every MCP call requires exact confirmation, including autonomous mode.
                    sensitive=(level >= 1),
                )

                def _make_caller(s=sess, tool_name=name):
                    def _call(params: dict) -> ToolResult:
                        return s.call_tool(tool_name, params)
                    return _call

                registry.register(spec, _make_caller())
                count += 1
        return count
