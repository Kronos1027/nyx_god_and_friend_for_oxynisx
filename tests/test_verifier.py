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
    check_ok = v.verify("write_file", {"path": str(target), "content": "conteúdo real"}, res_ok)
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


def test_write_verification_rejects_stale_content_and_directories(tmp_path):
    verifier = ActionVerifier()
    target = tmp_path / "existing.txt"
    target.write_bytes(b"old")
    result = ToolResult(ok=True, output="claimed success")
    assert not verifier.verify("write_file", {"path": str(target), "content": "new"}, result).verified
    assert not verifier.verify("write_file", {"path": str(tmp_path), "content": ""}, result).verified
    assert not verifier.verify("write_file", {"path": str(target), "content": ""}, result).verified


def test_write_verification_accepts_exact_utf8_and_empty_file(tmp_path):
    verifier = ActionVerifier()
    target = tmp_path / "text.txt"
    result = ToolResult(ok=True, output="written")
    for content in ("", "Olá\nNyx 🌙"):
        target.write_bytes(content.encode("utf-8"))
        assert verifier.verify("write_file", {"path": str(target), "content": content}, result).verified


def test_write_verification_uses_sandbox_resolved_relative_path(tmp_path):
    from tools.file_tool import FileTool
    params = {"path": "relative.txt", "content": "inside sandbox"}
    result = FileTool([tmp_path]).write_file(params)
    assert ActionVerifier().verify("write_file", params, result).verified
    assert not ActionVerifier().verify("write_file", params, ToolResult(True, "claimed")).verified
