"""Rust acceleration is optional, explicitly opted-in and never authoritative."""
import sys
import types

import pytest

from core.kra13_hot_memory import bounded_fact_prompt as baseline
from core.native_memory import bounded_fact_prompt as native_adapter


def test_python_remains_default_even_when_rust_module_is_installed(monkeypatch):
    called = []
    fake = types.SimpleNamespace(
        bounded_fact_prompt=lambda *args: called.append(True) or "unexpected"
    )
    monkeypatch.setitem(sys.modules, "nyx_memory_native", fake)
    monkeypatch.delenv("NYX_NATIVE_MEMORY", raising=False)
    facts = {"nyx_persona": "Assistente", "hardware_gpu": "RTX 3060"}
    assert native_adapter(facts, "RTX", 500) == baseline(facts, "RTX", 500)
    assert not called


def test_missing_native_module_falls_back_to_python(monkeypatch):
    monkeypatch.setenv("NYX_NATIVE_MEMORY", "1")
    monkeypatch.setitem(sys.modules, "nyx_memory_native", None)
    facts = {"security_policy": "Ações exigem aprovação", "name": "Nyx"}
    assert native_adapter(facts, "aprovacao", 350) == baseline(facts, "aprovacao", 350)


def test_native_divergence_in_compare_mode_never_changes_output(monkeypatch):
    monkeypatch.setenv("NYX_NATIVE_MEMORY", "1")
    monkeypatch.setenv("NYX_NATIVE_COMPARE", "1")
    fake = types.SimpleNamespace(bounded_fact_prompt=lambda *args: "wrong")
    monkeypatch.setitem(sys.modules, "nyx_memory_native", fake)
    facts = {"fact": "Correct memory"}
    assert native_adapter(facts, "memory", 1700) == baseline(facts, "memory", 1700)


def test_native_exception_falls_back_and_does_not_disable_memory(monkeypatch):
    monkeypatch.setenv("NYX_NATIVE_MEMORY", "1")
    def crashed(*args):
        raise RuntimeError("native experiment failed")
    monkeypatch.setitem(sys.modules, "nyx_memory_native",
                        types.SimpleNamespace(bounded_fact_prompt=crashed))
    facts = {"security_policy": "Requer consentimento"}
    assert native_adapter(facts, "consentimento", 500) == baseline(facts, "consentimento", 500)


def test_untrusted_values_have_original_behavior(monkeypatch):
    monkeypatch.delenv("NYX_NATIVE_MEMORY", raising=False)
    facts = {"valid": "valor", "invalid": 42}
    assert "valid" in native_adapter(facts, "", 500)
    assert "invalid" not in native_adapter(facts, "", 500)
    with pytest.raises(ValueError):
        native_adapter(facts, "", 299)
