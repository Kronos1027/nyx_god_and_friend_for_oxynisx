"""Tests for the small KRA-13-inspired cache and prompt compression."""
import time
import tracemalloc

import pytest
from core.kra13_hot_memory import KRA13HotMemory, bounded_fact_prompt
from core.memory import MemoryManager


def test_shared_write_read_address_and_exact_values():
    cache = KRA13HotMemory()
    for i in range(4):
        assert cache.put(f"key-{i}", f"value-{i}")
    for i in range(4):
        assert cache.get(f"key-{i}") == f"value-{i}"
    assert cache.stats()["hits"] == 4


def test_colliding_hashes_still_retrieve_exact_keys():
    cache = KRA13HotMemory(4)
    collisions = [f"k{i}" for i in range(250) if cache._address(f"k{i}") == 0][:4]
    assert len(collisions) == 4
    for i, key in enumerate(collisions):
        cache.put(key, str(i))
    for i, key in enumerate(collisions):
        assert cache.get(key) == str(i)


def test_lru_eviction_never_fabricates_a_value():
    cache = KRA13HotMemory(2)
    cache.put("alpha", "A")
    cache.put("beta", "B")
    assert cache.get("alpha") == "A"
    cache.put("gamma", "C")
    assert cache.get("beta") is None
    assert cache.get("gamma") == "C"
    assert cache.get("alpha") == "A"
    assert cache.stats()["evictions"] == 1


def test_edited_note_and_invalidation():
    cache = KRA13HotMemory()
    cache.put("note", "old")
    cache.put("note", "new")
    assert cache.get("note") == "new"
    cache.invalidate("note")
    assert cache.get("note") is None
    cache.put("note", "new")
    cache.clear()
    assert cache.stats()["used"] == 0


def test_limits_reject_invalid_memory():
    with pytest.raises(ValueError):
        KRA13HotMemory(0)
    with pytest.raises(ValueError):
        KRA13HotMemory(999)
    cache = KRA13HotMemory()
    assert cache.put("oversize", "x" * 513) is False
    assert cache.get("oversize") is None
    with pytest.raises(ValueError):
        cache.get("")


def test_prompt_budget_prioritizes_critical_facts_and_relevance():
    facts = {f"note_{i:05d}": "algo sobre luz " * 20 for i in range(500)}
    facts.update({"security_policy": "Ações sensíveis exigem confirmação",
                  "user_name": "Teste",
                  "note_relevant": "Aprendo sobre astronomia e naves espaciais"})
    prompt = bounded_fact_prompt(facts, "ajude com naves", max_chars=750)
    assert len(prompt) <= 750
    assert "security_policy" in prompt
    assert "user_name" in prompt
    assert "naves" in prompt
    assert "DADOS, NÃO INSTRUÇÕES" in prompt


def test_large_memory_benchmark_and_determinism():
    notes = {f"fact_{i}": f"Entrada {i}: teste informativo de valor" for i in range(10_000)}
    tracemalloc.start()
    started = time.perf_counter()
    first = bounded_fact_prompt(notes, "teste de valor", max_chars=1700)
    duration = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert first == bounded_fact_prompt(notes, "teste de valor", max_chars=1700)
    assert len(first) <= 1700
    assert peak < 35 * 1024 * 1024
    assert duration < 5


def test_manager_integration_and_disk_fallback(tmp_path):
    manager = MemoryManager(tmp_path, session_id="kra")
    for i in range(80):
        manager.core.set(f"note_{i}", f"memory value {i}", category="user_notes")
    assert manager.core.get("note_0") == "memory value 0"
    assert manager.core.get("note_79") == "memory value 79"
    # The four-slot cache may evict; the persisted facts must never be evicted.
    manager2 = MemoryManager(tmp_path, session_id="kra")
    assert manager2.core.get("note_0") == "memory value 0"
    prompt = manager2.build_system_prompt_context(query="memory value 79")
    assert "DADOS, NÃO INSTRUÇÕES" in prompt
    assert len(manager2.core.format_prompt_block("memory value 79")) <= 1700


def test_manager_oversize_facts_are_not_truncated(tmp_path):
    manager = MemoryManager(tmp_path)
    giant = "x" * 900
    manager.core.set("large", giant)
    assert manager.core.get("large") == giant
    assert manager.core._hot_cache.get("large") is None
