"""Fase 1 — testes do agent_loop (ciclo de decisão + segurança da seção 4).

Cobre: parse incerto → ação none + auditoria; política de confirmação
(destrutivo SEMPRE confirma, mesmo autônomo); modo autônomo só por fonte de
UI (texto é ILEGAL — seção 4.1); timeout automático; ciclo completo com
auditoria JSONL.
"""

import json

import pytest

from audit.logger import AuditLogger
from config import PermissionMode
from core.agent_loop import AgentLoop, SecurityError
from core.llm_client import OfflineLLM
from tools.file_tool import FileTool, make_file_tool_func
from tools.registry import ToolRegistry, ToolSpec
from tools.shell_tool import ShellTool, make_shell_tool_func


class FakeClock:
    """Relógio controlável pra testar o timeout do modo autônomo."""

    def __init__(self) -> None:
        self._now = 1000.0

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _resp(action=None, **over):
    payload = {
        "reasoning": "r",
        "alternative_suggestion": None,
        "emotion": "idle",
        "action": action or {"type": "none", "params": {}},
        "requires_confirmation": over.pop("requires_confirmation", False),
        "confirmation_prompt": over.pop("confirmation_prompt", None),
        "speech_output": over.pop("speech_output", "ok"),
    }
    return json.dumps(payload, ensure_ascii=False)


def make_loop(tmp_path, scripted=None, clock=None):
    audit = AuditLogger(tmp_path / "logs", session_id="test")
    registry = ToolRegistry()
    ft = FileTool([tmp_path / "sandbox"])
    shell = ShellTool(dialect="posix", timeout=10)
    registry.register(
        ToolSpec("shell", "comandos via allowlist", False, True,
                 destructive_probe=lambda p: shell.is_destructive(p.get("template", ""))),
        make_shell_tool_func(shell))
    registry.register(ToolSpec("read_file", "ler", False, False),
                      make_file_tool_func(ft, "read_file"))
    registry.register(ToolSpec("write_file", "escrever", False, True),
                      make_file_tool_func(ft, "write_file"))
    registry.register(ToolSpec("delete_file", "DESTRUTIVO", True, True),
                      make_file_tool_func(ft, "delete_file"))
    loop = AgentLoop(OfflineLLM(scripted or []), registry, audit,
                     mode=PermissionMode.ASSISTIDA, clock=clock)
    return loop, audit, registry


# ---------------------------------------------------------------------------
# Parse incerto → ação none + auditoria (seção 3.3)
# ---------------------------------------------------------------------------

def test_invalid_llm_output_results_in_no_action_and_audit(tmp_path):
    loop, audit, _ = make_loop(tmp_path, scripted=["{{{{não é json"])
    result = loop.process("faça algo")
    assert result.response.parse_ok is False
    assert result.response.action.type == "none"
    assert result.executed is False
    entries = audit.read_all()
    dec = [e for e in entries if e["event"] == "decision"][-1]
    assert dec["parse_ok"] is False
    assert dec["action_type"] == "none"
    assert dec["executed"] is False


def test_schema_violation_results_in_no_action(tmp_path):
    bad = json.dumps({"emotion": "furiosa", "action": "shell"})  # schema errado
    loop, audit, _ = make_loop(tmp_path, scripted=[bad])
    result = loop.process("faça algo")
    assert result.response.action.type == "none"
    assert result.response.parse_ok is False


# ---------------------------------------------------------------------------
# Ciclo completo com ação real + auditoria
# ---------------------------------------------------------------------------

def test_full_cycle_write_file_with_audit(tmp_path):
    """Ciclo completo em modo assistida: write_file é sensível -> confirmação
    -> aprovação via confirm_pending -> execução -> auditoria."""
    action = {"type": "write_file", "params": {"path": "a.txt", "content": "ola"}}
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(action=action,
                                     speech_output="Escrevi o arquivo.")])
    result = loop.process("escreve ola em a.txt")
    assert result.needs_confirmation is True  # sensível em modo assistida
    approved = loop.confirm_pending(result.pending_action, approved=True)
    assert approved.executed is True
    assert approved.tool_result.ok is True
    assert (tmp_path / "sandbox" / "a.txt").read_text(encoding="utf-8") == "ola"
    events = [e["event"] for e in audit.read_all()]
    assert "confirmed_execution" in events
    dec = [e for e in audit.read_all() if e["event"] == "decision"][-1]
    assert dec["mode"] == "assistida"


def test_llm_cannot_express_actions_outside_schema(tmp_path):
    """Camada 1 de defesa: o schema (seção 3.3) NÃO aceita tipos fora da
    lista — 'format_hd' nem chega a ser avaliado como ação."""
    action = {"type": "format_hd", "params": {}}
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(action=action)])
    result = loop.process("formata o hd")
    assert result.response.parse_ok is False
    assert result.response.action.type == "none"
    assert result.executed is False
    dec = [e for e in audit.read_all() if e["event"] == "decision"][-1]
    assert dec["parse_ok"] is False


def test_valid_type_unregistered_tool_is_blocked_and_flagged(tmp_path):
    """Camada 2 de defesa: 'ui_action' é tipo válido do schema (Fase 4),
    mas não está registrada no registry da Fase 1 -> fora da allowlist ->
    exige confirmação e não executa."""
    action = {"type": "ui_action", "params": {"target": "botão salvar"}}
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(action=action)])
    result = loop.process("clica em salvar")
    assert result.executed is False
    assert result.needs_confirmation is True
    dec = [e for e in audit.read_all() if e["event"] == "decision"][-1]
    assert dec["action_type"] == "ui_action"
    assert dec["executed"] is False


# ---------------------------------------------------------------------------
# Política de confirmação (seção 4.2)
# ---------------------------------------------------------------------------

def test_destructive_requires_confirmation_even_in_assisted(tmp_path):
    """Destrutivo via template shell (o schema não expressa deleção direta):
    DELETE_FILE é destructive -> confirmação SEMPRE."""
    target = tmp_path / "sandbox" / "a.txt"
    action = {"type": "shell", "params": {"template": "DELETE_FILE",
                                           "path": str(target)}}
    loop, _, _ = make_loop(tmp_path, scripted=[_resp(action=action)])  # cria a sandbox
    target.write_text("x")
    result = loop.process("deleta a.txt")
    assert result.executed is False
    assert result.needs_confirmation is True
    assert "DESTRUTIVA" in (result.confirmation_prompt or "")
    assert target.exists()  # nada foi apagado


def test_confirm_pending_executes_only_after_approval(tmp_path):
    target = tmp_path / "sandbox" / "a.txt"
    action = {"type": "shell", "params": {"template": "DELETE_FILE",
                                           "path": str(target)}}
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(action=action)])  # cria a sandbox
    target.write_text("x")
    first = loop.process("deleta a.txt")
    assert first.needs_confirmation is True

    denied = loop.confirm_pending(first.pending_action, approved=False)
    assert denied.executed is False
    assert target.exists()

    approved = loop.confirm_pending(first.pending_action, approved=True)
    assert approved.executed is True
    assert not target.exists()
    codes = [e["event"] for e in audit.read_all()]
    assert "confirmation_denied_by_user" in codes
    assert "confirmed_execution" in codes


def test_sensitive_tool_requires_confirmation_in_assisted_mode(tmp_path):
    action = {"type": "write_file", "params": {"path": "n.txt", "content": "x"}}
    loop, _, _ = make_loop(tmp_path, scripted=[_resp(action=action)])
    result = loop.process("escreve algo")
    assert result.needs_confirmation is True  # write_file é sensitive + assistida


# ---------------------------------------------------------------------------
# Modo autônomo (seção 4.1) — ativação só por UI, timeout automático
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("illegal_source", ["text", "voice_text", "llm_response", "chat"])
def test_autonomous_activation_by_text_is_illegal(tmp_path, illegal_source):
    loop, audit, _ = make_loop(tmp_path)
    with pytest.raises(SecurityError):
        loop.activate_autonomous(illegal_source)
    assert loop.mode is PermissionMode.ASSISTIDA
    sec = [e for e in audit.read_all() if e["event"] == "security"][-1]
    assert sec["code"] == "autonomous_activation_denied"


@pytest.mark.parametrize("legal_source", ["ui_toggle", "ui_hotkey"])
def test_autonomous_activation_by_ui_is_legal(tmp_path, legal_source):
    loop, _, _ = make_loop(tmp_path)
    loop.activate_autonomous(legal_source)
    assert loop.mode is PermissionMode.AUTONOMA


def test_autonomous_mode_executes_sensitive_without_confirmation(tmp_path):
    action = {"type": "write_file", "params": {"path": "auto.txt", "content": "x"}}
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(action=action)])
    loop.activate_autonomous("ui_toggle")
    result = loop.process("escreve algo")
    assert result.executed is True
    dec = [e for e in audit.read_all() if e["event"] == "decision"][-1]
    assert dec["mode"] == "autonoma"


def test_autonomous_mode_executes_non_destructive_shell_template(tmp_path):
    """Allowlisted e não-destrutivo em autônomo: executa direto (sem pedir nada)."""
    action = {"type": "shell", "params": {"template": "LIST_DIR", "path": "."}}
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(action=action)])
    loop.activate_autonomous("ui_toggle")
    result = loop.process("lista o diretório")
    assert result.executed is True
    assert result.tool_result.ok is True
    dec = [e for e in audit.read_all() if e["event"] == "decision"][-1]
    assert dec["mode"] == "autonoma" and dec["executed"] is True


def test_autonomous_timeout_returns_to_assisted(tmp_path):
    clock = FakeClock()
    action = {"type": "write_file", "params": {"path": "t.txt", "content": "x"}}
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(action=action)], clock=clock)
    loop.activate_autonomous("ui_toggle", ttl_seconds=1800)

    clock.advance(1799)
    result = loop.process("ainda autônoma?")
    assert loop.mode is PermissionMode.AUTONOMA
    assert result.executed is True

    clock.advance(2)  # passa do timeout (1801s total)
    loop.process("depois do timeout")
    assert loop.mode is PermissionMode.ASSISTIDA
    changes = [e for e in audit.read_all() if e["event"] == "mode_change"]
    assert any(c["source"] == "timeout" and c["new_mode"] == "assistida" for c in changes)


def test_destructive_still_requires_confirmation_in_autonomous(tmp_path):
    """REGRA NÃO-NEGOCIÁVEL (seção 4.2): destrutivo pede confirmação MESMO
    em modo autônomo. Este teste é a definition of done da Fase 5 aplicada
    desde já no núcleo."""
    target = tmp_path / "sandbox" / "a.txt"
    action = {"type": "shell", "params": {"template": "DELETE_FILE",
                                           "path": str(target)}}
    loop, _, _ = make_loop(tmp_path, scripted=[_resp(action=action)])  # cria a sandbox
    target.write_text("x")
    loop.activate_autonomous("ui_toggle")
    result = loop.process("deleta a.txt")
    assert loop.mode is PermissionMode.AUTONOMA
    assert result.needs_confirmation is True
    assert result.executed is False
    assert (tmp_path / "sandbox" / "a.txt").exists()


# ---------------------------------------------------------------------------
# Auditoria (seção 4.4) — JSONL append-only
# ---------------------------------------------------------------------------

def test_audit_log_is_jsonl_append_only(tmp_path):
    loop, audit, _ = make_loop(tmp_path, scripted=[_resp(), _resp()])
    loop.process("pergunta 1")
    loop.process("pergunta 2")
    raw = (tmp_path / "logs" / "nyx_audit_test.jsonl").read_text(encoding="utf-8")
    lines = [ln for ln in raw.strip().splitlines() if ln]
    assert len(lines) >= 2  # ao menos as 2 decisions
    for line in lines:
        entry = json.loads(line)
        assert "ts" in entry and "event" in entry


def test_history_is_kept_short(tmp_path):
    loop, _, _ = make_loop(tmp_path, scripted=[_resp()] * 20)
    for i in range(20):
        loop.process(f"pergunta {i}")
    assert len(loop.history) <= 12
