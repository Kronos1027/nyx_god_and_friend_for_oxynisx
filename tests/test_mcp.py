"""Testes do cliente MCP (Model Context Protocol)."""

from tools.mcp_client import MCPServerConfig, MCPClientSession, MCPManager
from tools.registry import ToolRegistry


def test_mcp_config_and_permissions():
    cfg = MCPServerConfig(
        server_id="filesystem",
        command=["python", "-m", "mock_server"],
        allowed_tools=["read_file", "list_dir"],
        permission_levels={"read_file": 0, "list_dir": 0, "delete_file": 3},
    )

    sess = MCPClientSession(cfg)

    # 1. Ferramenta fora da allowlist
    res_blocked = sess.call_tool("unauthorized_tool", {})
    assert res_blocked.ok is False
    assert "allowlist" in res_blocked.error

    # 2. Ferramenta de nível 3 (proibida)
    cfg.allowed_tools.append("delete_file")
    res_forbidden = sess.call_tool("delete_file", {})
    assert res_forbidden.ok is False
    assert "Nível 3" in res_forbidden.error


def test_mcp_manager_registry_population():
    mgr = MCPManager()
    cfg = MCPServerConfig(
        server_id="mock_srv",
        command=["python", "-c", "pass"],
        allowed_tools=["calc", "status"],
        permission_levels={"calc": 0, "status": 0},
    )
    mgr.register_server(cfg)

    # Cria sessão mockada
    sess = MCPClientSession(cfg)
    # Injeta mock list_tools
    sess.list_tools = lambda: [
        {"name": "calc", "description": "Calculadora"},
        {"name": "status", "description": "Status do sistema"},
    ]
    mgr.sessions["mock_srv"] = sess

    registry = ToolRegistry()
    registered = mgr.populate_registry(registry)
    assert registered == 2
    assert "mcp_mock_srv_calc" in registry.available_tools()
    assert "mcp_mock_srv_status" in registry.available_tools()
