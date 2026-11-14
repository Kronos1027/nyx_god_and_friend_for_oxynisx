"""Optional Rust selector with fully compatible Python fallback.

Disabled by default. Native code must pass parity tests on real workloads
before enabling by default; an extension import error never breaks Nyx.
"""
from __future__ import annotations

import logging
import os

from core.kra13_hot_memory import bounded_fact_prompt as python_fact_prompt

log = logging.getLogger(__name__)


def bounded_fact_prompt(facts: dict[str, str], query: str = "", max_chars: int = 1700) -> str:
    if os.getenv("NYX_NATIVE_MEMORY", "0") != "1":
        return python_fact_prompt(facts, query, max_chars)
    try:
        import nyx_memory_native
    except ImportError:
        return python_fact_prompt(facts, query, max_chars)

    # Compare mode is intended for the development bench and always returns
    # the Python result on divergence; never change policy/data on mismatch.
    try:
        result = nyx_memory_native.bounded_fact_prompt(
            facts, query, max_chars
        )
        if os.getenv("NYX_NATIVE_COMPARE", "0") == "1":
            expected = python_fact_prompt(facts, query, max_chars)
            if result != expected:
                log.warning("Nyx Rust memory selector diverged from Python; using baseline.")
                return expected
        return result
    except (ValueError, TypeError, RuntimeError, OverflowError):
        # Never let an optional accelerator take down memory assembly.
        return python_fact_prompt(facts, query, max_chars)
