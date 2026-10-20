"""Fase 1 — testes do macro_tool (store de skills gravadas).

Cobre: salvar/listar/carregar macros, replay via registry, bloqueio de
passo destrutivo durante replay, nomes inválidos rejeitados.
"""

import pytest

from tools.macro_tool import MacroError, MacroStore, make_macro_tool_func
from tools.registry import ToolRegistry, ToolSpec
from tools.file_tool import FileTool, make_file_tool_func


@pytest.fixture
def registry(tmp_path):
    reg = ToolRegistry()
    ft = FileTool([tmp_path / "sandbox"])
    reg.register(ToolSpec("write_file", "escrever", False, True),
                 make_file_tool_func(ft, "write_file"))
    reg.register(ToolSpec("read_file", "ler", False, False),
                 make_file_tool_func(ft, "read_file"))
    reg.register(ToolSpec("delete_file", "DESTRUTIVO", True, True),
                 make_file_tool_func(ft, "delete_file"))
    return reg


@pytest.fixture
def store(tmp_path):
    return MacroStore(tmp_path / "macros")


def test_save_and_load_roundtrip(store):
    steps = [{"tool": "write_file", "params": {"path": "a.txt", "content": "x"}}]
    path = store.save("backup-diario", steps)
    assert path.exists()
    assert store.load("backup-diario") == steps


def test_list_macros_sorted(store, registry):
    store.save("beta", [{"tool": "read_file", "params": {"path": "x"}}])
    store.save("alpha", [{"tool": "read_file", "params": {"path": "y"}}])
    assert store.list_macros() == ["alpha", "beta"]


@pytest.mark.parametrize("bad_name", [
    "NOME_MAIUSCULO", "tem espaço", "../traversal", "nome/slash",
    "", "-comeca-hifen", "a" * 60, 123,
])
def test_invalid_macro_names_are_rejected(store, bad_name):
    with pytest.raises(MacroError):
        store.save(bad_name, [{"tool": "read_file", "params": {}}])


def test_invalid_steps_are_rejected(store):
    with pytest.raises(MacroError):
        store.save("ok-name", [])                       # vazio
    with pytest.raises(MacroError):
        store.save("ok-name", [{"sem_tool": True}])     # sem tool
    with pytest.raises(MacroError):
        store.save("ok-name", [{"tool": "x", "params": "não-dict"}])  # params inválido
    with pytest.raises(MacroError):
        store.save("ok-name", [{"tool": "x", "params": {}}] * 51)     # max 50 passos


def test_replay_executes_steps_via_registry(store, registry):
    store.save("cria-notas", [
        {"tool": "write_file", "params": {"path": "n1.txt", "content": "1"}},
        {"tool": "write_file", "params": {"path": "n2.txt", "content": "2"}},
    ])
    results = store.replay("cria-notas", registry)
    assert all(r.ok for r in results), [r.error for r in results]


def test_replay_stops_on_destructive_step(store, registry):
    store.save("macro-perigosa", [
        {"tool": "write_file", "params": {"path": "ok.txt", "content": "1"}},
        {"tool": "delete_file", "params": {"path": "ok.txt"}},
    ])
    results = store.replay("macro-perigosa", registry)
    assert results[0].ok is True                      # primeiro passo rodou
    assert results[1].ok is False                     # destrutivo BLOQUEADO no replay
    assert results[1].meta["needs_confirmation"] is True


def test_replay_unknown_tool_returns_error_result(store, registry):
    store.save("macro-quebrada", [{"tool": "ferramenta_fantasma", "params": {}}])
    results = store.replay("macro-quebrada", registry)
    assert results[0].ok is False
    assert "desconhecida" in results[0].error


def test_missing_macro_raises_clean_error(store):
    with pytest.raises(MacroError):
        store.load("nunca-existi")


def test_make_macro_tool_func_ops(store, registry):
    func = make_macro_tool_func(store, registry)
    r = func({"op": "save", "name": "demo", "steps": [
        {"tool": "write_file", "params": {"path": "d.txt", "content": "v"}}]})
    assert r.ok is True
    r = func({"op": "list"})
    assert "demo" in r.output
    r = func({"op": "run", "name": "demo"})
    assert r.ok is True
    r = func({"op": "op_invalida"})
    assert r.ok is False
