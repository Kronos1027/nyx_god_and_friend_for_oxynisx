"""Nyx harness: bounded, explicit, evidence-based goal postconditions.

Unlike a model saying "done", this checks a requested artifact against the
filesystem. Contracts are supplied by trusted application code, not generated
by an LLM or inferred from untrusted tool output. No model or network needed.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

MAX_VERIFY_BYTES = 8 * 1024 * 1024
_ALLOWED_KINDS = frozenset(("file_sha256", "file_absent"))


@dataclass(frozen=True)
class GoalVerdict:
    status: str
    reason: str
    kind: str

    @property
    def passed(self) -> bool:
        return self.status == "VERIFIED"


@dataclass(frozen=True)
class GoalContract:
    kind: str
    path: str
    sha256: str | None = None

    @classmethod
    def parse(cls, value: Mapping, roots: Sequence[str | Path]) -> "GoalContract":
        if not isinstance(value, dict) or value.get("kind") not in _ALLOWED_KINDS:
            raise ValueError("Pós-condição desconhecida.")
        required = {"kind", "path", "sha256"} if value["kind"] == "file_sha256" else {"kind", "path"}
        if set(value) != required:
            raise ValueError("Campos inválidos para a pós-condição.")
        path, digest = value["path"], value.get("sha256")
        if not isinstance(path, str) or not 1 <= len(path) <= 4096:
            raise ValueError("Caminho inválido.")
        if not os.path.isabs(path):
            raise ValueError("Caminho da pós-condição precisa ser absoluto.")
        if value["kind"] == "file_sha256" and (
            not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
        ):
            raise ValueError("SHA-256 inválido.")
        if not isinstance(roots, (tuple, list)) or not roots:
            raise ValueError("Pós-condição exige raízes autorizadas do aplicativo.")
        destination = Path(path).resolve()
        if not any(destination.is_relative_to(Path(root).resolve()) for root in roots):
            raise ValueError("Pós-condição fora das raízes autorizadas.")
        return cls(value["kind"], str(destination), digest.lower() if digest is not None else None)

    def as_dict(self) -> dict:
        result = {"kind": self.kind, "path": self.path}
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        return result

    def evaluate(self, steps: Sequence[Mapping], roots: Sequence[str | Path]) -> GoalVerdict:
        # Revalidate persisted contracts: roots and symlink targets may change
        # between restart and execution. Never trust stored path blindly.
        try:
            current = self.parse(self.as_dict(), roots)
        except (ValueError, OSError, RuntimeError):
            return GoalVerdict("UNVERIFIED", "outside_authorized_roots", self.kind)

        # A preexisting state, or a model assertion, does not prove that
        # this *task* made the requested change.
        witness_tool = "write_file" if self.kind == "file_sha256" else "delete_file"
        witnessed = False
        for step in steps:
            if (step.get("tool") != witness_tool or step.get("ok") is not True
                    or step.get("verified") is not True):
                continue
            params = step.get("params", {})
            if not isinstance(params, dict) or not isinstance(params.get("path"), str):
                continue
            if not os.path.isabs(params["path"]):
                continue
            try:
                if str(Path(params["path"]).resolve()) == current.path:
                    witnessed = True
                    break
            except (ValueError, OSError, RuntimeError):
                continue
        if not witnessed:
            reason = "no_verified_write" if self.kind == "file_sha256" else "no_verified_delete"
            return GoalVerdict("UNVERIFIED", reason, self.kind)

        try:
            target = Path(current.path)
            if self.kind == "file_absent":
                try:
                    target.lstat()
                except FileNotFoundError:
                    return GoalVerdict("VERIFIED", "file_absent", self.kind)
                return GoalVerdict("UNVERIFIED", "file_still_exists", self.kind)
            # Limit reads and reject directories or giant files. Opening on
            # Windows remains subject to normal filesystem ACLs; this is not
            # an OS-level sandbox or protection from concurrent TOCTOU races.
            if not target.is_file():
                return GoalVerdict("UNVERIFIED", "file_missing", self.kind)
            size = target.stat().st_size
            if size < 0 or size > MAX_VERIFY_BYTES:
                return GoalVerdict("UNVERIFIED", "file_too_large", self.kind)
            with target.open("rb") as stream:
                digest = hashlib.sha256()
                total = 0
                while True:
                    chunk = stream.read(min(65536, MAX_VERIFY_BYTES + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_VERIFY_BYTES:
                        return GoalVerdict("UNVERIFIED", "file_too_large", self.kind)
                    digest.update(chunk)
            return GoalVerdict(
                "VERIFIED" if digest.hexdigest() == self.sha256 else "UNVERIFIED",
                "exact_sha256" if digest.hexdigest() == self.sha256 else "hash_mismatch",
                self.kind,
            )
        except (OSError, ValueError, RuntimeError):
            return GoalVerdict("UNVERIFIED", "read_failed", self.kind)
