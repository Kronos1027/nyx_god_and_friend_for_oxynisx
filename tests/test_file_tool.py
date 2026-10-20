"""Fase 1 — testes do file_tool com sandbox (seção 4.3).

Cobre: leitura/escrita/busca/deleção reais dentro da sandbox; bloqueio de
traversal (../), paths absolutos externos e acesso fora das raízes.
"""


import pytest

from tools.file_tool import FileTool, SandboxViolation, make_file_tool_func


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "nyx_root"
    root.mkdir()
    return FileTool([root])


@pytest.fixture
def outside(tmp_path):
    out = tmp_path / "fora_da_sandbox"
    out.mkdir()
    return out


# ---------------------------------------------------------------------------
# Operações permitidas (execução REAL de IO)
# ---------------------------------------------------------------------------

def test_write_and_read_roundtrip(sandbox):
    r1 = sandbox.write_file({"path": "docs/nota.txt", "content": "linha 1\nlinha 2"})
    assert r1.ok is True, r1.error
    r2 = sandbox.read_file({"path": "docs/nota.txt"})
    assert r2.ok is True
    assert r2.output == "linha 1\nlinha 2"


def test_find_files_with_glob(sandbox):
    sandbox.write_file({"path": "a.py", "content": "x=1"})
    sandbox.write_file({"path": "sub/b.py", "content": "y=2"})
    sandbox.write_file({"path": "sub/c.txt", "content": "z"})
    r = sandbox.find_files({"pattern": "**/*.py"})
    assert r.ok is True
    assert r.meta["count"] == 2
    assert any(p.endswith("a.py") for p in r.output.splitlines())


def test_delete_file_inside_sandbox(sandbox):
    sandbox.write_file({"path": "temp.txt", "content": "x"})
    r = sandbox.delete_file({"path": "temp.txt"})
    assert r.ok is True
    r2 = sandbox.read_file({"path": "temp.txt"})
    assert r2.ok is False


def test_read_missing_file_fails_cleanly(sandbox):
    r = sandbox.read_file({"path": "fantasma.txt"})
    assert r.ok is False


# ---------------------------------------------------------------------------
# Sandbox: tudo fora das raízes é BLOQUEADO (seção 4.3)
# ---------------------------------------------------------------------------

def test_traversal_escape_is_blocked(sandbox):
    with pytest.raises(SandboxViolation):
        sandbox.read_file({"path": "../fora.txt"})
    with pytest.raises(SandboxViolation):
        sandbox.write_file({"path": "../../etc/passwd", "content": "x"})


def test_absolute_path_outside_is_blocked(sandbox, outside):
    with pytest.raises(SandboxViolation):
        sandbox.read_file({"path": str(outside / "segredo.txt")})
    with pytest.raises(SandboxViolation):
        sandbox.write_file({"path": str(outside / "injecao.txt"), "content": "x"})


def test_symlink_escape_is_blocked(sandbox, outside):
    # symlink dentro da sandbox apontando pra fora deve ser rejeitado
    link = sandbox.roots[0] / "link_malicioso"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks indisponíveis neste ambiente")
    with pytest.raises(SandboxViolation):
        sandbox.write_file({"path": link / "vazou.txt", "content": "x"})


def test_empty_roots_is_forbidden(tmp_path):
    with pytest.raises(ValueError):
        FileTool([])


def test_multiple_roots_first_match_wins(tmp_path):
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    r1.mkdir(), r2.mkdir()
    ft = FileTool([r1, r2])
    assert ft.write_file({"path": str(r2 / "b.txt"), "content": "ok"}).ok is True
    with pytest.raises(SandboxViolation):
        ft.read_file({"path": str(tmp_path / "r3" / "c.txt")})


# ---------------------------------------------------------------------------
# Fábrica do registry
# ---------------------------------------------------------------------------

def test_make_file_tool_func_dispatch(sandbox):
    write = make_file_tool_func(sandbox, "write_file")
    read = make_file_tool_func(sandbox, "read_file")
    assert write({"path": "x.txt", "content": "oi"}).ok is True
    assert read({"path": "x.txt"}).output == "oi"
    with pytest.raises(ValueError):
        make_file_tool_func(sandbox, "format_hd")
