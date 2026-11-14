"""Evidence-based next-experiment suggestions, NOT self-modifying behavior.

Never enables tools, trains weights, executes follow-up tasks, or declares
statistical significance from a small sample. Suggestions only.
"""
from __future__ import annotations

from collections import Counter
from typing import Mapping, Sequence


def propose_followup_research(trials: Sequence[Mapping], summary: Mapping) -> list[dict]:
    if not isinstance(trials, (list, tuple)) or not isinstance(summary, dict):
        raise ValueError("Dados de avaliação inválidos")
    reasons = Counter(item.get("reason") for item in trials if isinstance(item, dict))
    denials = sum(min(10, item.get("denials", 0)) for item in trials if
                  isinstance(item, dict) and type(item.get("denials")) is int and item["denials"] >= 0)
    low_mem = any(
        isinstance(item, dict)
        and isinstance(item.get("resources"), dict)
        and type(item["resources"].get("min_system_available_mib")) in (int, float)
        and item["resources"]["min_system_available_mib"] < 3200
        for item in trials
    )
    proposals = []

    def add(focus, why, test):
        proposals.append({"focus": focus, "evidence": why, "next_experiment": test})

    if low_mem or any(isinstance(x, dict) and x.get("failure_class") in
                      ("InferencePressureError", "BackendUnavailable", "MemoryError") for x in trials):
        add("R04_memory_headroom",
            "Pressão ou pouca RAM disponível foi observada; isso não prova causa exclusiva.",
            "Comparar 1024/2048/4096 tokens com um modelo residente, medindo RAM e erros.")
    if denials:
        add("R06_approval_boundaries",
            "Houve propostas recusadas pelo controlador de autorização.",
            "Inspecionar apenas os códigos de recusa; não relaxar permissões automaticamente.")
    if reasons.get("hash_mismatch", 0):
        add("R01_exact_output",
            "Houve ações verificadas cujo conteúdo final não correspondeu ao esperado.",
            "Testar Unicode, quebras de linha e cópia de arquivos sem correção pelo modelo.")
    if reasons.get("no_verified_write", 0):
        add("R02_action_planning",
            "O executor não observou uma escrita válida para algumas metas.",
            "Comparar prompts de ferramenta e planejamento, sem aumentar o número de agentes.")
    if len(trials) < 40:
        add("R00_sample_size",
            "Amostra exploratória pequena, sem significância estatística demonstrada.",
            "Ampliar o conjunto retido com seeds e ordem alternada antes de promover mudanças.")
    else:
        delta = summary.get("paired_delta_pp")
        if type(delta) in (int, float) and delta <= 0:
            add("R03_harness_latency",
                "O harness candidato não mostrou ganho pareado positivo nesta amostra.",
                "Comparar latência, tokens e recuperação em casos de falha antes de mudar o modelo.")
    return proposals[:5]
