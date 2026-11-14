"""Evidence-only task health report for Nyx desktop and local automation.

A verified tool action is never conflated with a verified *goal*. No personal
strings, paths, prompts, outputs, or secrets are included in a health report.
No model calls and no filesystem effects.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from core.task_reliability import StepEvidence, trailing_failures

_SAFE_STATES = frozenset({
    "PLAN", "ACT", "OBSERVE", "PAUSED", "RESOURCE_PRESSURE",
    "WAITING_USER", "WAITING_REVIEW", "FAILED",
    "CANCELLED", "PLANNING_FINISHED",
})


def task_health(record: Mapping) -> dict:
    if not isinstance(record, dict):
        raise ValueError("Registro de tarefa inválido.")
    state = record.get("state")
    if state not in _SAFE_STATES:
        state = "UNKNOWN"
    steps = record.get("steps", [])
    if not isinstance(steps, list) or len(steps) > 48:
        raise ValueError("Histórico de passos fora dos limites da Nyx.")
    evidence = StepEvidence.inspect(steps)
    verdict = record.get("goal_verdict")
    has_contract = isinstance(record.get("goal_contract"), dict)
    kind = (
        str(record["goal_contract"].get("kind", ""))[:40] if has_contract else None
    )
    goal_ok = (
        isinstance(verdict, dict)
        and verdict.get("status") == "VERIFIED"
    )
    uncertain = bool(record.get("uncertain") or record.get("inflight") or state == "WAITING_REVIEW")
    redacted = bool(record.get("redacted"))
    safe_resume = (
        state in {"PAUSED", "RESOURCE_PRESSURE"}
        and not uncertain and not redacted
    )
    if uncertain:
        status = "NEEDS_MANUAL_REVIEW"
        guidance = "Uma ação pode ter produzido efeito incerto; verifique manualmente antes de novo pedido."
    elif state == "WAITING_USER":
        status = "WAITING_CONFIRMATION"
        guidance = "Uma ação aguarda autorização; não execute automaticamente."
    elif state == "RESOURCE_PRESSURE":
        status = "RESOURCE_PAUSED"
        guidance = "Aguarde memória livre; a retomada exige ação explícita."
    elif state in {"PAUSED", "ACT", "PLAN", "OBSERVE"}:
        status = "IN_PROGRESS"
        guidance = "Revise o histórico e continue somente sob autorização e orçamento existentes."
    elif state in {"FAILED", "CANCELLED"}:
        status = "INTERRUPTED"
        guidance = "A tarefa foi interrompida; resultados anteriores não comprovam a meta inteira."
    elif state == "PLANNING_FINISHED" and has_contract and goal_ok:
        status = "GOAL_VERIFIED"
        guidance = "Todas as pós-condições declaradas foram verificadas; isso não prova correção semântica geral."
    elif state == "PLANNING_FINISHED" and has_contract:
        status = "GOAL_UNVERIFIED"
        guidance = "O planejador encerrou, mas a entrega declarada não foi totalmente verificada."
    elif state == "PLANNING_FINISHED":
        status = "NO_GOAL_CONTRACT"
        guidance = "Há apenas relatório de execução; a conclusão da meta não foi comprovada."
    else:
        status = "UNKNOWN"
        guidance = "Revise o estado original antes de continuar."

    return {
        "state": state,
        "status": status,
        "contract_kind": kind,
        "goal_verified": bool(status == "GOAL_VERIFIED"),
        "has_goal_contract": has_contract,
        "steps_total": evidence.attempted,
        "steps_verified": evidence.verified,
        "steps_failed": evidence.failed,
        "steps_uncertain": evidence.uncertain,
        "consecutive_tool_failures": trailing_failures(steps),
        "requires_manual_review": uncertain,
        "can_offer_resume": safe_resume,
        "guidance": guidance,
    }
