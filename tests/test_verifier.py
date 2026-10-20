"""Testes para o módulo ActionVerifier e Taxonomia de Falhas (Fase 1)."""

from core.verifier import ActionVerifier, ErrorTaxonomy
from tools.registry import ToolResult


def test_verifier_diagnose_command_not_found():
    v = ActionVerifier()
    res = ToolResult(ok=False, error="Comando 'notepad_xyz' não encontrado no sistema.")
    diag = v.verify("ui_action", {"action": "open_app", "app": "notepad_xyz"}, res)
    assert diag.verified is False
    assert diag.taxonomy_error == ErrorTaxonomy.COMMAND_NOT_FOUND
    assert diag.suggested_recovery_route is not None
    assert "registro" in diag.suggested_recovery_route.lower() or "navegador" in diag.suggested_recovery_route.lower()


def test_verifier_diagnose_permission_denied():
    v = ActionVerifier()
    res = ToolResult(ok=False, error="Acesso negado: permissão insuficiente para gravar.")
    diag = v.verify("write_file", {"path": "C:\\Windows\\System32\\test.dll"}, res)
    assert diag.verified is False
    assert diag.taxonomy_error == ErrorTaxonomy.PERMISSION_DENIED


def test_verifier_diagnose_timeout():
    v = ActionVerifier()
    res = ToolResult(ok=False, error="Operação excedeu o tempo limite (timed out).")
    diag = v.verify("web", {"action": "fetch", "url": "https://slow-site.com"}, res)
    assert diag.verified is False
    assert diag.taxonomy_error == ErrorTaxonomy.TIMEOUT


def test_verifier_write_file(tmp_path):
    v = ActionVerifier()
    target = tmp_path / "teste_verif.txt"
    target.write_text("conteúdo real", encoding="utf-8")

    # Arquivo existe -> verificado
    res_ok = ToolResult(ok=True, output=f"Escrito em {target}")
    check_ok = v.verify("write_file", {"path": str(target)}, res_ok)
    assert check_ok.verified is True
    assert "verificado em disco" in check_ok.details.lower()

    # Arquivo inexistente -> falha de verificação
    check_fail = v.verify("write_file", {"path": str(tmp_path / "fantasma.txt")}, res_ok)
    assert check_fail.verified is False
    assert check_fail.taxonomy_error == ErrorTaxonomy.INVALID_OUTPUT


def test_verifier_empty_output():
    v = ActionVerifier()
    res_empty = ToolResult(ok=True, output="   ")
    check = v.verify("generic_tool", {}, res_empty)
    assert check.verified is False
    assert check.taxonomy_error == ErrorTaxonomy.INVALID_OUTPUT
