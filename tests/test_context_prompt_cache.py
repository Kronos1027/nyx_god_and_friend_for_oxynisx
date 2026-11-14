"""Memory view cache integration: no stale facts, no extra model or resources."""
import threading

import pytest

from core.context_prompt_cache import ContextPromptCache
from core.kra13_hot_memory import bounded_fact_prompt as python_selector
from core.memory import MemoryManager


def test_cache_is_bounded_and_correct_lru():
    cache = ContextPromptCache(max_entries=2)
    assert cache.put("a", "first")
    assert cache.put("b", "second")
    assert cache.get("a") == "first"
    assert cache.put("c", "third")
    assert cache.get("b") is None
    assert cache.get("a") == "first"
    assert cache.get("c") == "third"
    assert cache.stats()["evictions"] == 1
    assert cache.stats()["used"] == 2


def test_cache_bounds_keys_values_and_validates_configuration():
    cache = ContextPromptCache(max_entries=2, max_key_chars=5, max_value_chars=300)
    assert not cache.put("012345", "small")
    assert not cache.put("ok", "x" * 301)
    assert not cache.put(None, "data")
    assert cache.get("012345") is None
    assert cache.stats()["used"] == 0
    for args in ({"max_entries": 0}, {"max_value_chars": 299},
                 {"max_key_chars": 0}, {"max_entries": True}):
        with pytest.raises(ValueError):
            ContextPromptCache(**args)


def test_repeated_prompt_uses_cache_and_new_fact_invalidates(monkeypatch, tmp_path):
    from core import native_memory
    mgr = MemoryManager(tmp_path)
    count = []
    original = native_memory.bounded_fact_prompt
    def instrumented(*args, **kwargs):
        count.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(native_memory, "bounded_fact_prompt", instrumented)
    first = mgr.core.format_prompt_block("galáxia")
    second = mgr.core.format_prompt_block("galáxia")
    assert first == second
    assert len(count) == 1
    mgr.core.set("note_unique", "galáxia observável para revisão")
    updated = mgr.core.format_prompt_block("galáxia")
    assert "note_unique" in updated
    assert len(count) == 2
    assert mgr.core._prompt_cache.stats()["used"] == 1


def test_sqlite_failed_write_does_not_mutate_facts_or_prompt_cache(monkeypatch, tmp_path):
    mgr = MemoryManager(tmp_path)
    mgr.core.set("note", "original")
    before = mgr.core.format_prompt_block("original")
    stats = mgr.core._prompt_cache.stats()
    def fail(*args):
        raise OSError("fake database failure")
    monkeypatch.setattr(mgr.store, "set_fact", fail)
    with pytest.raises(OSError):
        mgr.core.set("note", "corrupted")
    assert mgr.core.get("note") == "original"
    assert mgr.core.format_prompt_block("original") == before
    assert mgr.core._prompt_cache.stats()["hits"] == stats["hits"] + 1
    assert mgr.core._prompt_cache.stats()["used"] == 1


def test_memory_view_matches_baseline_for_nonrepeated_queries(tmp_path):
    mgr = MemoryManager(tmp_path)
    for i in range(100):
        mgr.core.set(f"fact_{i:03d}", f"Informação número {i} sobre astronomia")
    for query in ("astronomia", "Windows", "fato 22", "Windows", "astronomia"):
        assert mgr.core.format_prompt_block(query) == python_selector(
            mgr.core.all(), query, max_chars=1700
        )


def test_cache_does_not_store_unbounded_queries(tmp_path):
    mgr = MemoryManager(tmp_path)
    huge = "X" * 10_000
    expected = python_selector(mgr.core.all(), huge)
    for _ in range(2):
        assert mgr.core.format_prompt_block(huge) == expected
    assert mgr.core._prompt_cache.stats()["used"] == 0


def test_parallel_reads_writes_return_consistent_versions(tmp_path):
    mgr = MemoryManager(tmp_path)
    mgr.core.set("note", "version_0")
    errors = []
    def read_worker():
        try:
            for _ in range(80):
                result = mgr.core.format_prompt_block("version")
                if "version_0" not in result and "version_1" not in result:
                    errors.append("missing committed version")
        except Exception as exc:
            errors.append(type(exc).__name__)
    readers = [threading.Thread(target=read_worker) for _ in range(4)]
    for t in readers:
        t.start()
    mgr.core.set("note", "version_1")
    for t in readers:
        t.join(timeout=5)
    assert not errors
    assert all(not t.is_alive() for t in readers)
    assert "version_1" in mgr.core.format_prompt_block("version")
