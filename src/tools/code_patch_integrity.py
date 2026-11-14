"""Integrity of model-proposed code edits before/after a test executor.

No test execution, network, model or path creation. This checks exactly the
planned files, not unexpected side effects outside the edit set. It is a
postcondition for *bytes*, not evidence that a program behaves correctly.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


class PatchIntegrityError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Integridade do patch não confirmada: {code}.")


def patch_manifest(edits) -> list[dict]:
    """Trusted digest of the validated edits. No source bytes in manifest."""
    entries = []
    for edit in edits:
        raw = edit.content.encode("utf-8")
        if len(raw) > 200_000:
            raise PatchIntegrityError("SOURCE_TOO_LARGE")
        entries.append({
            "path": edit.relative,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return entries


def verify_applied_patch(edits, expected: list[dict]) -> bool:
    """Reject missing, symlinked, oversized or unexpectedly modified files."""
    if not isinstance(expected, list) or len(edits) != len(expected):
        raise PatchIntegrityError("INVALID_MANIFEST")
    for edit, record in zip(edits, expected):
        if not isinstance(record, dict) or record.get("path") != edit.relative:
            raise PatchIntegrityError("TARGET_CHANGED")
        target = Path(edit.path)
        try:
            if target.is_symlink() or not target.is_file():
                raise PatchIntegrityError("TARGET_NOT_REGULAR_FILE")
            # Limit actual read to 200001 bytes even if stat was checked.
            with target.open("rb") as stream:
                raw = stream.read(200_001)
            if len(raw) > 200_000:
                raise PatchIntegrityError("TARGET_TOO_LARGE")
            digest = hashlib.sha256(raw).hexdigest()
            if len(raw) != record.get("bytes") or digest != record.get("sha256"):
                raise PatchIntegrityError("HASH_MISMATCH")
        except OSError:
            raise PatchIntegrityError("TARGET_UNREADABLE") from None
    return True
