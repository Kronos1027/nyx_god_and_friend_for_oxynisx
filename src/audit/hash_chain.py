"""Nyx AGI Desktop v3 — audit/hash_chain.py (Log de Auditoria Hash-Chain Inviolável)

Registra todas as ações, decisões, evidências e proveniências em encadeamento
criptográfico SHA-256 append-only.
Qualquer modificação retroativa, exclusão ou truncamento quebra a cadeia de hashes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def canonical_json(data: Dict[str, Any]) -> str:
    """Gera representação canônica ordenada em JSON para hashing determinístico."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class HashChainLogger:
    """Gravador de log auditável com encadeamento de hash SHA-256."""

    def __init__(self, log_dir: str | Path = "logs", session_id: str = "main") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.log_dir / f"nyx_audit_chain_{session_id}.jsonl"
        self._last_hash = self._recover_last_hash()
        self._index = self._recover_last_index()

    def _recover_last_hash(self) -> str:
        """Lê o último hash da cadeia persistida ou inicia com raiz neutra."""
        if not self.file_path.exists():
            return "0" * 64
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines:
                    last_obj = json.loads(lines[-1])
                    return last_obj.get("hash", "0" * 64)
        except Exception:
            pass
        return "0" * 64

    def _recover_last_index(self) -> int:
        if not self.file_path.exists():
            return 0
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines:
                    last_obj = json.loads(lines[-1])
                    return int(last_obj.get("i", 0)) + 1
        except Exception:
            pass
        return 0

    def record(
        self,
        actor: str,
        action: str,
        args: Dict[str, Any],
        decision: str = "auto",
        provenance: Optional[List[str]] = None,
        result: Optional[Any] = None,
        evidence: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Grava uma entrada encadeada antes de qualquer efeito colateral."""
        args_str = canonical_json(args)
        args_hash = hashlib.sha256(args_str.encode("utf-8")).hexdigest()

        entry: Dict[str, Any] = {
            "i": self._index,
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "args_hash": f"sha256:{args_hash}",
            "provenance": provenance or ["trusted:user"],
            "decision": decision,
            "result": str(result) if result is not None else "",
            "evidence": evidence or {},
            "prev": self._last_hash,
        }

        # Calcula o hash da entrada canônica excluindo o próprio campo 'hash'
        block_hash = hashlib.sha256(canonical_json(entry).encode("utf-8")).hexdigest()
        entry["hash"] = block_hash

        # Grava em modo append imediato
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()

        self._last_hash = block_hash
        self._index += 1
        return entry

    @classmethod
    def verify_chain(cls, file_path: str | Path) -> Tuple[bool, int, Optional[str]]:
        """Verifica a integridade completa da cadeia de hashes.

        Retorna: (integro, total_blocos_validados, erro_se_houver)
        """
        p = Path(file_path)
        if not p.exists():
            return False, 0, f"Arquivo {file_path} não encontrado."

        expected_prev = "0" * 64
        count = 0

        with open(p, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except Exception as exc:
                    return False, count, f"Linha {line_no} contém JSON corrompido: {exc}"

                stored_hash = data.get("hash")
                stored_prev = data.get("prev")

                if stored_prev != expected_prev:
                    return (
                        False,
                        count,
                        f"Quebra de encadeamento na linha {line_no}: prev {stored_prev} != esperado {expected_prev}",
                    )

                # Recomputa hash sem a chave 'hash'
                to_hash = {k: v for k, v in data.items() if k != "hash"}
                calc_hash = hashlib.sha256(canonical_json(to_hash).encode("utf-8")).hexdigest()

                if calc_hash != stored_hash:
                    return (
                        False,
                        count,
                        f"Hash adulterado na linha {line_no}: gravado {stored_hash} != calculado {calc_hash}",
                    )

                expected_prev = stored_hash
                count += 1

        return True, count, None
