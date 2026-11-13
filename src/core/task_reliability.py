"""Pure, bounded reliability signals for multi-step Nyx tasks.

Signals describe evidence rather than grant permissions, execute actions, or
claim semantic goal completion. Unknown external effects are handled by the
runner's existing no-replay guard, never by these suggestions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

# Require an external effect or a tool observation before crediting commands as done.
_EXTERNAL_VERBS = re.compile(
    r"^\s*(?:por favor[,]?\s+|nyx[,]?\s+|pode\s+)?"
    r"(?:abra|abrir|instale|instalar|execute|executar|rode|rodar|"
    r"salve|salvar|grave|gravar|mova|mover|envie|enviar|"
    r"apague|apagar|exclua|excluir|clique|clicar|"
    r"baixe|baixar|configure|configurar|publique|publicar|"
    r"edite|editar|atualize|atualizar|acesse|acessar)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StepEvidence:
    attempted: int
    succeeded: int
    verified: int
    failed: int
    uncertain: int

    @classmethod
    def inspect(cls, steps: Sequence[Mapping]) -> "StepEvidence":
        return cls(
            attempted=len(steps),
            succeeded=sum(bool(s.get("ok")) for s in steps),
            verified=sum(bool(s.get("ok")) and s.get("verified") is True for s in steps),
            failed=sum(not bool(s.get("ok")) or s.get("verified") is False for s in steps),
            uncertain=sum(bool(s.get("ok")) and s.get("verified") is None for s in steps),
        )

    @property
    def has_verified_action(self) -> bool:
        return self.verified > 0


def trailing_failures(steps: Sequence[Mapping], *, same_tool: bool = True) -> int:
    """Stop consecutive failures, never count successful intermediate progress."""
    if not steps:
        return 0
    last_tool = steps[-1].get("tool")
    count = 0
    for step in reversed(steps):
        if same_tool and step.get("tool") != last_tool:
            break
        if step.get("ok") and step.get("verified") is True:
            break
        count += 1
    return count


def recovery_hint(step: Mapping) -> str:
    """Give the planner safe, tool-specific alternatives without raw outputs."""
    tool = str(step.get("tool", "ferramenta"))[:48]
    kind = {
        "read_file": "Confira o caminho e a existência do arquivo antes de nova leitura.",
        "find_files": "Refine o escopo e confirme as raízes de busca autorizadas.",
        "browser": "Inspecione URL, seletor e carregamento atual; evite repetir cliques.",
        "ui_action": "Observe novamente a janela ativa e o alvo antes de prosseguir.",
        "shell": "Verifique as permissões, dependências e saída; não repita efeitos incertos.",
        "agent_team": "Examine os resultados das subtarefas e investigue a dependência falha.",
        "code_task": "Leia os testes e a falha antes de propor outra alteração.",
    }.get(tool, "Reavalie os parâmetros, o estado real e uma alternativa segura.")
    return (
        f"A última ação ({tool}) não teve sucesso/verificação. {kind} "
        "Não presuma que houve mudança; não repita ações com efeito externo incerto. "
        "Se não houver um caminho seguro, informe a pendência ao usuário."
    )


def requires_external_action(goal: str) -> bool:
    return isinstance(goal, str) and bool(_EXTERNAL_VERBS.search(goal))


def should_replan_premature_finish(
    goal: str, steps: Sequence[Mapping], *, action_type: str,
    speech: str, tool_names: Sequence[str], attempts: int,
) -> bool:
    """At most one extra *planning* turn, never an automatic external effect."""
    if attempts >= 1 or action_type != "none" or not requires_external_action(goal):
        return False
    if StepEvidence.inspect(steps).has_verified_action:
        return False
    # A genuine refusal or lack of available tools must not trigger a loop.
    if re.search(r"\\b(?:não posso|não consigo|impossível|sem permissão|preciso de autorização)\\b",
                 str(speech), re.IGNORECASE):
        return False
    capable = frozenset((
        "ui_action", "browser", "write_file", "shell", "code_task",
        "project", "workspace", "clipboard", "git", "macro",
    ))
    return any(name in capable for name in tool_names)


def completion_warning(goal: str, steps: Sequence[Mapping], *, parse_ok: bool) -> str:
    """Warn instead of declaring an unobserved external command completed."""
    if not parse_ok or not requires_external_action(goal):
        return ""
    evidence = StepEvidence.inspect(steps)
    if evidence.attempted == 0:
        return (
            "Não executei nenhuma ferramenta nesta tarefa; "
            "a alteração solicitada não foi comprovada."
        )
    if not evidence.has_verified_action:
        return (
            "Nenhuma ação teve resultado verificado. "
            "Confira o estado antes de considerar a tarefa concluída."
        )
    return ""
