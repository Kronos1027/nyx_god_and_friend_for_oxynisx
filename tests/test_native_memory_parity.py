"""Parity of the Rust accelerator versus original Python memory selector.

This module is deliberately skipped when the Rust wheel is not installed.
The separate native CI job installs the wheel and must pass these tests.
"""
import random
import statistics
import time

import pytest

native = pytest.importorskip("nyx_memory_native")
from core.kra13_hot_memory import bounded_fact_prompt as baseline  # noqa: E402


@pytest.mark.parametrize("query, facts, cap", [
    ("naves", {"user_name": "Teste", "favorite_game": "naves espaciais",
               "security_policy": "Somente ações autorizadas"}, 350),
    ("astronomia", {"astronomia": "Exploração de estrelas e galáxias",
                    "nyx_persona": "Ajudante tranquila", "cidade": "Belo Horizonte"}, 700),
    ("português e café", {"a": "café delicioso", "b": "linguagem português",
                          "c": "correção de tarefas"}, 500),
    ("windows RTX", {"user_name": "Usuário", "system_os": "Windows 11",
                     "hardware_gpu": "RTX 3060", "mouse": "mover cursor"}, 300),
    ("", {}, 1700),
    ("nave", {"bad_value": 42, "key": "foguete nave", "x": None}, 1700),
])
def test_native_matches_python_on_known_inputs(query, facts, cap):
    assert native.bounded_fact_prompt(facts, query, cap) == baseline(facts, query, cap)


def test_native_ranking_is_deterministic_and_bounded_on_10000_facts():
    facts = {f"fact_{i:05d}": f"Pesquisa de memória e estrelas, informação {i}" for i in range(10_000)}
    facts["security_policy"] = "Ações importantes exigem consentimento"
    facts["user_name"] = "Teste"
    facts["active_project"] = "Nyx"
    result = native.bounded_fact_prompt(facts, "memória estrelas", 1700)
    assert result == baseline(facts, "memória estrelas", 1700)
    assert len(result) <= 1700
    assert result == native.bounded_fact_prompt(facts, "memória estrelas", 1700)
    assert "security_policy" in result
    assert "user_name" in result


def test_native_equivalence_with_randomized_ascii_and_portuguese():
    rng = random.Random(42)
    values = ["nave espacial", "pasta de músicas", "Python e Rust",
              "importância das estrelas", "GPU RTX 3060",
              "resultado verificado", "cidade de Moeda", "memória curta"]
    for _ in range(15):
        facts = {f"k{i:03d}": rng.choice(values) for i in range(350)}
        query = rng.choice(values)
        cap = rng.choice((300, 500, 750, 1700))
        assert native.bounded_fact_prompt(facts, query, cap) == baseline(facts, query, cap)


def test_rejects_invalid_native_budget():
    for bad in (0, 100, 8193):
        with pytest.raises(ValueError):
            native.bounded_fact_prompt({"k": "v"}, "", bad)


def test_measure_without_promising_a_speedup():
    facts = {f"key_{i:05d}": f"linha informação {i} com estrelas e galáxias"
             for i in range(3000)}
    times = {}
    for label, impl in (("python", baseline), ("rust", native.bounded_fact_prompt)):
        trials = []
        for _ in range(4):
            started = time.perf_counter()
            got = impl(facts, "estrelas galáxias", 1700)
            trials.append(time.perf_counter() - started)
            assert len(got) <= 1700
        times[label] = statistics.median(trials)
    # Measuring is mandatory; no arbitrary speedup assertion across CI machines.
    assert times["rust"] > 0 and times["python"] > 0



def test_special_unicode_casefold_divergence_uses_guarded_python_result(monkeypatch):
    """Rust Unicode lowercase is not guaranteed to match Python casefold."""
    from core.native_memory import bounded_fact_prompt as guarded
    facts = {"a": "Große Straße", "b": "STRASSE"}
    expected = baseline(facts, "strasse", 500)
    monkeypatch.setenv("NYX_NATIVE_MEMORY", "1")
    monkeypatch.setenv("NYX_NATIVE_COMPARE", "1")
    assert guarded(facts, "strasse", 500) == expected
    # A future implementation may achieve exact Unicode parity; either way,
    # the guard must never change the reference result.
