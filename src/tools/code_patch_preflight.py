"""Bounded static code preflight. Never imports or executes project code.

It checks Python syntax, JSON and TOML parsing using trusted standard-library
parsers. Text/YAML/other formats are explicitly UNSCANNED, not marked valid.
It cannot establish test success, safety, or functional correctness.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path, PurePosixPath
import tomllib
from typing import Iterable

MAX_SOURCE_BYTES = 200_000
MAX_PLAN_FILES = 5
MAX_INSPECT_FILES = 12

_FORMATS = {".py": "python", ".json": "json", ".toml": "toml"}


class PatchPreflightError(ValueError):
    def __init__(self, code: str, path: str | None = None, line: int | None = None):
        self.code = code
        self.path = path
        self.line = line
        # No compiler/parser exception text or untrusted source is exposed.
        label = f" no arquivo {path}" if path else ""
        line_info = f" (linha {line})" if type(line) is int and line > 0 else ""
        super().__init__(f"Verificação estática: {code}{label}{line_info}.")


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PatchPreflightError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def check_source(relative: str, content: str) -> dict:
    """Return parser evidence without ever returning file contents."""
    if not isinstance(relative, str) or not isinstance(content, str):
        raise PatchPreflightError("INVALID_INPUT")
    if len(content.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise PatchPreflightError("SOURCE_TOO_LARGE", relative)
    suffix = PurePosixPath(relative.replace("\\", "/")).suffix.lower()
    kind = _FORMATS.get(suffix)
    if kind is None:
        return {"path": relative, "format": "other", "status": "UNSCANNED"}
    try:
        if kind == "python":
            ast.parse(content, filename="<nyx-preflight>", mode="exec")
        elif kind == "json":
            json.loads(content, object_pairs_hook=_reject_duplicate_pairs)
        else:
            tomllib.loads(content)
    except PatchPreflightError as exc:
        raise PatchPreflightError(exc.code, relative) from None
    except SyntaxError as exc:
        raise PatchPreflightError("PYTHON_SYNTAX", relative, exc.lineno) from None
    except json.JSONDecodeError as exc:
        raise PatchPreflightError("JSON_SYNTAX", relative, exc.lineno) from None
    except tomllib.TOMLDecodeError as exc:
        line = getattr(exc, "lineno", None)
        raise PatchPreflightError("TOML_SYNTAX", relative, line) from None
    except (ValueError, RecursionError, MemoryError):
        raise PatchPreflightError("PARSER_REJECTED", relative) from None
    return {"path": relative, "format": kind, "status": "PARSED"}


def check_edit_batch(edits: Iterable) -> list[dict]:
    """Check all proposed edits as a single batch before any edit is applied."""
    edits = list(edits)
    if not 1 <= len(edits) <= MAX_PLAN_FILES:
        raise PatchPreflightError("INVALID_BATCH_SIZE")
    seen = set()
    reports = []
    for edit in edits:
        relative = edit.relative
        # Windows is case-insensitive by default; fail conservatively on Linux
        # too to avoid a generated plan that changes semantics on Windows.
        normalized = str(PurePosixPath(relative.replace("\\", "/"))).casefold()
        if normalized in seen:
            raise PatchPreflightError("DUPLICATE_TARGET", relative)
        seen.add(normalized)
        reports.append(check_source(relative, edit.content))
    return reports


def inspect_existing_files(repo: Path, files: object) -> list[dict]:
    """Inspect only explicit files inside the caller-authorized repository.

    The caller performs the normal Nyx tool permission check before invoking
    this. This is not a filesystem sandbox against adversarial symlink races.
    """
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_INSPECT_FILES:
        raise PatchPreflightError("FILES_MUST_BE_LIST_1_TO_12")
    repo = Path(repo).resolve(strict=True)
    seen = set()
    reports = []
    for item in files:
        if not isinstance(item, str) or not item or len(item) > 256:
            raise PatchPreflightError("INVALID_RELATIVE_PATH")
        relative = item.replace("\\", "/")
        posix = PurePosixPath(relative)
        if (posix.is_absolute() or ":" in relative or
                any(part in (".", "..") for part in posix.parts)):
            raise PatchPreflightError("PATH_OUTSIDE_REPOSITORY")
        key = str(posix).casefold()
        if key in seen:
            raise PatchPreflightError("DUPLICATE_TARGET")
        seen.add(key)
        requested = repo / Path(*posix.parts)
        # Reject all symlink components including links pointing back into repo.
        path = repo
        for part in posix.parts:
            path = path / part
            if path.is_symlink():
                raise PatchPreflightError("SYMLINK_DISALLOWED")
        try:
            target = requested.resolve(strict=True)
            if not target.is_relative_to(repo):
                raise PatchPreflightError("PATH_OUTSIDE_REPOSITORY")
            if not target.is_file() or target.stat().st_size > MAX_SOURCE_BYTES:
                raise PatchPreflightError("FILE_NOT_SMALL_REGULAR_FILE", relative)
            raw = target.read_bytes()
            if len(raw) > MAX_SOURCE_BYTES:
                raise PatchPreflightError("SOURCE_TOO_LARGE", relative)
            content = raw.decode("utf-8-sig")
        except (OSError, UnicodeError, ValueError) as exc:
            if isinstance(exc, PatchPreflightError):
                raise
            raise PatchPreflightError("FILE_NOT_READABLE", relative) from None
        reports.append(check_source(str(posix), content))
    return reports
