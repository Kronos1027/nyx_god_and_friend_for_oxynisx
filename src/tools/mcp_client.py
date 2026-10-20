"""Nyx — tools/mcp_client.py (Cliente MCP para Servidores Externos)

Implementa cliente local do Model Context Protocol (MCP) via JSON-RPC stdio:
- Handshake protocolar (initialize, notifications/initialized, tools/list, tools/call)
- Whitelist estrita por servidor e por ferramenta com controle de permissão em camadas (0, 1, 2, 3)
- Integração transparente com o ToolRegistry da Nyx
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tools.registry import ToolResult, ToolSpec

log = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    server_id: str
    command: List[str]
    allowed_tools: List[str] = field(default_factory=list)
    permission_levels: Dict[str, int] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)


class MCPClientSession:
    """Sessão de comunicação JSON-RPC com um servidor MCP em subprocess."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.proc: Optional[subprocess.Popen] = None
        self._msg_id = 0

    def start(self) -> bool:
        try:
            self.proc = subprocess.Popen(
                self.config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            # Handshake MCP
            init_res = self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "NyxAgent", "version": "3.0"},
                },
            )
            if "error" in init_res:
                log.error(f"[MCP] Erro no handshake: {init_res['error']}")
                return False

            self._send_notification("notifications/initialized", {})
            return True
        except Exception as exc:
            log.error(f"[MCP] Falha ao iniciar servidor '{self.config.server_id}': {exc}")
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
            if self.config.allowed_tools:
                return [t for t in raw_tools if t.get("name") in self.config.allowed_tools]
            return raw_tools
        return []

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        if self.config.allowed_tools and name not in self.config.allowed_tools:
            return ToolResult(
                ok=False,
                error=f"Ferramenta '{name}' não está na allowlist do servidor MCP '{self.config.server_id}'.",
            )

        level = self.config.permission_levels.get(name, 2)
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
            meta={"server": self.config.server_id, "level": level},
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
        self.servers[config.server_id] = config

    def connect_all(self) -> Dict[str, bool]:
        status = {}
        for s_id, cfg in self.servers.items():
            sess = MCPClientSession(cfg)
            if sess.start():
                self.sessions[s_id] = sess
                status[s_id] = True
            else:
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
                if not name:
                    continue
                desc = t.get("description", f"Ferramenta MCP do servidor {s_id}")
                full_name = f"mcp_{s_id}_{name}"
                level = sess.config.permission_levels.get(name, 1)

                spec = ToolSpec(
                    name=full_name,
                    description=desc,
                    destructive=(level >= 2),
                    sensitive=(level >= 1),
                )

                def _make_caller(s=sess, tool_name=name):
                    def _call(params: dict) -> ToolResult:
                        return s.call_tool(tool_name, params)
                    return _call

                registry.register(spec, _make_caller())
                count += 1
        return count
