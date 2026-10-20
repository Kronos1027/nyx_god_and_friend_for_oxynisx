"""Fase 1 — testes do shell_tool com allowlist (seção 4.2).

Cobre: bloqueio de comando fora da allowlist, validação de parâmetros
(injection/traversal), flag destrutiva sempre confirmável, e execução REAL
posix no CI (lista de args, sem shell=True).
"""

import pytest

from tools.shell_tool import (
    ShellBlockedError,
    ShellTool,
    make_shell_tool_func,
    validate_param,
)


@pytest.fixture
def shell():
    return ShellTool(dialect="posix", timeout=10)


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------

def test_unknown_template_is_blocked(shell):
    with pytest.raises(ShellBlockedError) as e:
        shell.run_template("FORMAT_DISK", {})
    assert e.value.reason == "fora_da_allowlist"


def test_unknown_template_reason_is_outside_allowlist(shell):
    with pytest.raises(ShellBlockedError):
        shell.run_template("Remove-Item -Recurse -Force C:/", {})
    assert shell.template_names() == [
        "DELETE_FILE", "DISK_FREE", "GET_FILE_INFO", "GET_PROCESS",
        "KILL_PROCESS_BY_NAME", "LIST_DIR",
    ]


def test_missing_and_extra_params_are_blocked(shell):
    with pytest.raises(ShellBlockedError):
        shell.run_template("LIST_DIR", {})  # faltando path
    with pytest.raises(ShellBlockedError):
        shell.run_template("LIST_DIR", {"path": ".", "evil": "x"})  # extra


def test_destructive_flag_is_explicit(shell):
    assert shell.is_destructive("KILL_PROCESS_BY_NAME") is True
    for safe in ("LIST_DIR", "GET_FILE_INFO", "GET_PROCESS", "DISK_FREE"):
        assert shell.is_destructive(safe) is False, f"{safe} não pode ser destrutivo"


# ---------------------------------------------------------------------------
# Validação de parâmetros (anti-injection)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "a; rm -rf /",            # encadeamento
    "a | whoami",             # pipe
    "a & echo x",             # and-chain
    "`whoami`",               # command substitution
    "$(whoami)",              # command substitution
    "${PATH}",                # var expansion
    "path/../../etc",         # traversal
    "com 'aspas'",            # aspas (escape de contexto PS)
    'com "aspas"',            # aspas duplas
    "linha\nnova",            # newline
    "-flag",                  # argument injection (começa com -)
    "x" * 300,                # exagero de tamanho
])
def test_validate_param_rejects_dangerous_values(value):
    with pytest.raises(ShellBlockedError):
        validate_param("path", "path", value)


@pytest.mark.parametrize("value", ["C:/Users/fulano", "documents/arquivos", "notepad.exe"])
def test_validate_param_accepts_benign_values(value):
    assert validate_param("path", "path", value) == value


def test_kill_process_params_are_validated(shell):
    with pytest.raises(ShellBlockedError):
        shell.run_template("KILL_PROCESS_BY_NAME", {"name": "a; shutdown /r"})


def test_powershell_dialect_is_also_validated(shell_ps):
    # Mesmo o dialeto Windows passa pela MESMA validação de params.
    with pytest.raises(ShellBlockedError):
        shell_ps.run_template("LIST_DIR", {"path": "../../windows/system32/config"})
    with pytest.raises(ShellBlockedError):
        shell_ps.run_template("NÃO_EXISTE", {})


@pytest.fixture
def shell_ps():
    return ShellTool(dialect="powershell", timeout=10)


# ---------------------------------------------------------------------------
# Execução REAL (posix, CI Linux) — prova de execução da Fase 1
# ---------------------------------------------------------------------------

def test_real_execution_list_dir(shell, tmp_path):
    (tmp_path / "arquivo_a.txt").write_text("a")
    (tmp_path / "arquivo_b.txt").write_text("b")
    result = shell.run_template("LIST_DIR", {"path": str(tmp_path)})
    assert result.ok is True, result.error
    assert "arquivo_a.txt" in result.output
    assert result.meta["template"] == "LIST_DIR"
    assert result.meta["argv"][0] == "ls"  # lista de args, SEM shell=True


def test_real_execution_disk_free(shell):
    result = shell.run_template("DISK_FREE", {})
    assert result.ok is True, result.error
    assert result.output != ""


def test_real_execution_nonexistent_path_fails_cleanly(shell, tmp_path):
    result = shell.run_template("LIST_DIR", {"path": str(tmp_path / "nao_existe")})
    assert result.ok is False
    assert result.error  # mensagem de erro presente, sem estourar exceção


# ---------------------------------------------------------------------------
# Adaptador do registry
# ---------------------------------------------------------------------------

def test_make_shell_tool_func_requires_template(shell):
    func = make_shell_tool_func(shell)
    result = func({})
    assert result.ok is False
    assert "template" in (result.error or "")


def test_make_shell_tool_func_blocks_unknown_template(shell):
    func = make_shell_tool_func(shell)
    result = func({"template": "DEL_TREE", "path": "."})
    assert result.ok is False
    assert "fora_da_allowlist" in (result.error or "")
