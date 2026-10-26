"""Nyx — tools/mcp_client.py (Cliente MCP para Servidores Externos)

Política de ferramentas MCP e adaptador legado, ainda sem transporte isolado.
Inicialização de servidores no host está bloqueada até integrar isolamento,
aprovação do servidor e timeouts efetivos. Não conectado ao runtime principal.
"""

from __future__ import annotations

import json
import re
from types import MappingProxyType
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.proc: Optional[subprocess.Popen] = None
        self._msg_id = 0
        self.last_error = None

    def start(self) -> bool:
        # A command in configuration is not permission to execute arbitrary code
        # with the host user's filesystem, network and credential access.
        self.last_error = "Servidor MCP não iniciado: transporte isolado com aprovação ainda não integrado."
        log.warning("[MCP] %s", self.last_error)
        return False

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                self.proc.kill()
        self.proc = None

    def list_tools(self) -> List[Dict[str, Any]]:
        res = self._send_request("tools/list", {})
        if "result" in res and "tools" in res["result"]:
            raw_tools = res["result"]["tools"]
            # Filtra apenas ferramentas presentes na whitelist configurada
            if not isinstance(raw_tools, list) or len(raw_tools) > 128:
                return []
            return [t for t in raw_tools if isinstance(t, dict)
                    and isinstance(t.get("name"), str)
                    and t.get("name") in self.config.allowed_tools
                    and self.config.permission_levels.get(t.get("name"), 3) < 3]
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
            return ToolResult(ok=False, error=str(res["error"]))

        result = res.get("result", {})
        content_items = result.get("content", [])
        output_parts = []
        for item in content_items:
            if item.get("type") == "text":
                output_parts.append(item.get("text", ""))
            else:
                output_parts.append(str(item))

        out_text = "\n".join(output_parts) or json.dumps(result, ensure_ascii=False)
        return ToolResult(
            ok=not result.get("isError", False),
            output=out_text,
            meta={"server": self.config.server_id, "level": level, "untrusted_data": True},
        )

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            return {"error": "Servidor MCP desconectado."}

        self._msg_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params,
        }
        try:
            line = json.dumps(msg) + "\n"
            self.proc.stdin.write(line)
            self.proc.stdin.flush()

            resp_line = self.proc.stdout.readline()
            if not resp_line:
                return {"error": "Resposta vazia do servidor MCP."}
            return json.loads(resp_line.strip())
        except Exception as exc:
            return {"error": f"Erro de comunicação JSON-RPC: {exc}"}

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            return
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        try:
            line = json.dumps(msg) + "\n"
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except Exception:
            pass


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
