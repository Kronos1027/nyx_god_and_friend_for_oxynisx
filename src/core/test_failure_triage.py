"""Pure classification of test-run output, without exposing source or secrets.

Output is untrusted text, even when received from a real test executor:
malicious projects can print fake "passed" summaries or instructions.
Only a trusted runner's exit code is considered for success/failure.
"""
from __future__ import annotations

import re

_MAX_CHARS = 12_000
_CATEGORIES = (
    ("DEPENDENCY_MISSING", re.compile(r"\b(?:ModuleNotFoundError|No module named|ImportError)\b", re.I)),
    ("SYNTAX_ERROR", re.compile(r"\b(?:SyntaxError|IndentationError|TabError)\b", re.I)),
    ("ASSERTION_FAILED", re.compile(r"\b(?:AssertionError|assert\s+False|FAILED\s+\S+::)\b", re.I)),
    ("TIMEOUT", re.compile(r"\b(?:TimeoutExpired|TimeoutError|timed out|deadline exceeded)\b", re.I)),
    ("PERMISSION_DENIED", re.compile(r"\b(?:PermissionError|Access is denied|Permission denied)\b", re.I)),
)


def classify_test_result(exit_code: object, output: object) -> dict:
    """Classify symptoms only; never treat log text as a test pass verdict."""
    if type(exit_code) is not int or not -999 <= exit_code <= 999:
        raise ValueError("Código de término inválido do executor.")
    if not isinstance(output, str):
        raise ValueError("Saída inválida do executor.")
    excerpt = output[-_MAX_CHARS:]
    if exit_code == 0:
        category = "EXECUTOR_EXIT_ZERO"
    else:
        category = next((name for name, pattern in _CATEGORIES if pattern.search(excerpt)),
                        "UNCLASSIFIED_FAILURE")
    return {
        "status": "EXIT_ZERO" if exit_code == 0 else "NONZERO_EXIT",
        "category": category,
        "exit_code": exit_code,
        "output_characters": min(len(output), 1_000_000),
        "truncated": len(output) > _MAX_CHARS,
        "untrusted_output": True,
    }
