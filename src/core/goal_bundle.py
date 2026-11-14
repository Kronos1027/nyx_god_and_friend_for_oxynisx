"""Trusted multi-artifact postconditions for Nyx code/project tasks.

A single verified write does *not* prove completion of a project requiring
code, tests, and configuration. The application (not the LLM) creates this
small finite list of SHA-256 checks; all must pass. No effects are executed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from core.goal_contract import GoalContract, GoalVerdict

MAX_ITEMS = 8


@dataclass(frozen=True)
class GoalBundle:
    items: tuple[GoalContract, ...]
    kind: str = "file_bundle"

    @classmethod
    def parse(cls, value: Mapping, roots: Sequence[str | Path]) -> "GoalBundle":
        if not isinstance(value, dict) or set(value) != {"kind", "items"}:
            raise ValueError("Contrato de múltiplos arquivos inválido.")
        if value["kind"] != "file_bundle" or not isinstance(value["items"], list):
            raise ValueError("Tipo de pós-condição composta inválido.")
        if not 2 <= len(value["items"]) <= MAX_ITEMS:
            raise ValueError("Informe de 2 a 8 arquivos, sem contratos aninhados.")
        items: list[GoalContract] = []
        paths: set[str] = set()
        for part in value["items"]:
            contract = GoalContract.parse(part, roots)
            if contract.kind != "file_sha256":
                raise ValueError("O conjunto aceita apenas hashes de arquivos gravados.")
            # Reject duplicate targets, including aliases after realpath resolution.
            normalized = os.path.normcase(contract.path)
            if normalized in paths:
                raise ValueError("O conjunto contém caminhos de arquivo duplicados.")
            paths.add(normalized)
            items.append(contract)
        return cls(tuple(items))

    def as_dict(self) -> dict:
        return {"kind": self.kind, "items": [c.as_dict() for c in self.items]}

    def evaluate(self, steps, roots) -> GoalVerdict:
        verified = 0
        for item in self.items:
            if item.evaluate(steps, roots).passed:
                verified += 1
        if verified == len(self.items):
            return GoalVerdict("VERIFIED", "all_files_verified", self.kind)
        # Return only counts, not private file paths or content in audit/UI.
        return GoalVerdict("UNVERIFIED", f"verified_{verified}_of_{len(self.items)}", self.kind)


def parse_goal_contract(spec: Mapping, roots: Sequence[str | Path]) -> GoalContract | GoalBundle:
    """Strict trusted contract parser shared by start and crash recovery."""
    if isinstance(spec, dict) and spec.get("kind") == "file_bundle":
        return GoalBundle.parse(spec, roots)
    return GoalContract.parse(spec, roots)


def required_goal_tool(contract: GoalContract | GoalBundle) -> str:
    """This is never a permission grant, only a replan eligibility check."""
    return "delete_file" if contract.kind == "file_absent" else "write_file"
