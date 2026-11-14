"""Tiny bounded, thread-safe LRU for immutable memory prompt strings.

This is a *derived view* of CoreMemory facts, never an authoritative
database/cache for the facts themselves. Invalidate on every accepted write.
No disk, network, model inference or background thread.
"""
from __future__ import annotations

import threading
from collections import OrderedDict


class ContextPromptCache:
    def __init__(self, *, max_entries: int = 8, max_value_chars: int = 1700,
                 max_key_chars: int = 256):
        if type(max_entries) is not int or not 1 <= max_entries <= 32:
            raise ValueError("max_entries must be 1..32")
        if type(max_value_chars) is not int or not 300 <= max_value_chars <= 8192:
            raise ValueError("max_value_chars must be 300..8192")
        if type(max_key_chars) is not int or not 1 <= max_key_chars <= 2048:
            raise ValueError("max_key_chars must be 1..2048")
        self.max_entries = max_entries
        self.max_value_chars = max_value_chars
        self.max_key_chars = max_key_chars
        self._items: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, query: str) -> str | None:
        if not isinstance(query, str) or len(query) > self.max_key_chars:
            return None
        with self._lock:
            value = self._items.get(query)
            if value is None:
                self.misses += 1
                return None
            self.hits += 1
            self._items.move_to_end(query)
            return value

    def put(self, query: str, output: str) -> bool:
        if (not isinstance(query, str) or len(query) > self.max_key_chars
                or not isinstance(output, str) or len(output) > self.max_value_chars):
            return False
        with self._lock:
            self._items[query] = output
            self._items.move_to_end(query)
            if len(self._items) > self.max_entries:
                self._items.popitem(last=False)
                self.evictions += 1
            return True

    def invalidate(self) -> None:
        with self._lock:
            self._items.clear()

    def stats(self) -> dict:
        with self._lock:
            return {
                "capacity": self.max_entries, "used": len(self._items),
                "hits": self.hits, "misses": self.misses,
                "evictions": self.evictions,
                "max_cached_characters": self.max_entries * self.max_value_chars,
            }
