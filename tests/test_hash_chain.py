"""Testes da Fase 0.6: Log de Auditoria Hash-Chain Inviolável (audit/hash_chain.py)"""

import json
from pathlib import Path

from audit.hash_chain import HashChainLogger


def test_hash_chain_integrity(tmp_path: Path):
    logger = HashChainLogger(log_dir=tmp_path, session_id="test_chain")

    # 1. Grava 5 blocos encadeados
    e1 = logger.record("user", "prompt", {"text": "Inicie o sistema"}, "auto", ["trusted:user"])
    e2 = logger.record("planner", "plan", {"steps": 3}, "auto", ["trusted:planner"])
    e3 = logger.record("tool", "ui_action", {"action": "open_app", "app": "notepad"}, "auto")
    e4 = logger.record("tool", "file_operation", {"path": "test.txt", "content": "dados"}, "auto")
    e5 = logger.record("planner", "final_answer", {"message": "Finalizado"}, "auto")

    assert e1["prev"] == "0" * 64
    assert e2["prev"] == e1["hash"]
    assert e3["prev"] == e2["hash"]
    assert e4["prev"] == e3["hash"]
    assert e5["prev"] == e4["hash"]

    # 2. Validação da cadeia íntegra
    valid, count, err = HashChainLogger.verify_chain(logger.file_path)
    assert valid is True
    assert count == 5
    assert err is None


def test_hash_chain_tamper_detection(tmp_path: Path):
    logger = HashChainLogger(log_dir=tmp_path, session_id="tamper_test")

    logger.record("user", "action1", {"param": 1})
    logger.record("tool", "action2", {"param": 2})
    logger.record("tool", "action3", {"param": 3})

    # Simula adulteração maliciosa da linha 2
    with open(logger.file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    tampered_entry = json.loads(lines[1])
    tampered_entry["action"] = "malicious_injected_action"
    lines[1] = json.dumps(tampered_entry) + "\n"

    with open(logger.file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    # Verificação deve falhar e apontar adulteração
    valid, count, err = HashChainLogger.verify_chain(logger.file_path)
    assert valid is False
    assert "adulterado" in err.lower() or "quebra" in err.lower()
