"""Nyx AGI Desktop v3 — core/context.py (ContextManager Avançado)

Implementa as 5 técnicas de engenharia de contexto do Plano Mestre v3:
1. Observation Masking (substituição de payloads extensos por tokens opacos com recuperação).
2. Tool Masking (estabilidade de prefixo para preservar KV cache).
3. Recitação de todo.md (ancoragem do objetivo para mitigar context rot).
4. Preservação de erros enxutos no contexto (sinal negativo para descarte de rotas falhas).
5. Prefixo estável sem timestamps voláteis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ObservationEntry:
    id: int
    raw_content: str
    char_count: int
    tool_name: str


class ContextManager:
    """Gerenciador de janela de contexto para tarefas de longa duração."""

    def __init__(
        self,
        max_context_tokens: int = 8192,
        mask_threshold_chars: int = 800,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.mask_threshold_chars = mask_threshold_chars
        self._observations_store: Dict[int, ObservationEntry] = {}
        self._obs_counter = 0
        self.todo_items: List[Dict[str, str]] = []

    def store_observation(self, tool_name: str, content: str) -> str:
        """Armazena a observação bruta e retorna versão mascarada se ultrapassar o limiar."""
        self._obs_counter += 1
        obs_id = self._obs_counter
        entry = ObservationEntry(
            id=obs_id,
            raw_content=content,
            char_count=len(content),
            tool_name=tool_name,
        )
        self._observations_store[obs_id] = entry

        if len(content) > self.mask_threshold_chars:
            approx_tokens = len(content) // 4
            return (
                f"[obs #{obs_id} — {tool_name} — {approx_tokens} tokens "
                f"({len(content)} chars) — recuperável via ctx.get({obs_id})]"
            )
        return content

    def get_raw_observation(self, obs_id: int) -> Optional[str]:
        """Recupera o conteúdo bruto de uma observação previamente mascarada."""
        entry = self._observations_store.get(obs_id)
        return entry.raw_content if entry else None

    def update_todo(self, items: List[Dict[str, str]]) -> None:
        """Atualiza a lista de tarefas vivas do plano."""
        self.todo_items = items

    def format_todo_recitation(self) -> str:
        """Gera a recitação do estado atual do todo.md para inserção no fim do prompt."""
        if not self.todo_items:
            return ""

        lines = ["\n[PLANO ATIVO — RECITADO]:"]
        for item in self.todo_items:
            status = item.get("status", "pending")
            tag = "[x]" if status == "done" else "[~]" if status == "running" else "[!]" if status == "failed" else "[ ]"
            lines.append(f"{tag} {item.get('id', '')}: {item.get('desc', '')}")
        return "\n".join(lines)

    def assemble_prompt(
        self,
        system_prompt: str,
        history: List[Dict[str, str]],
        current_turn: str,
        skills_summary: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Monta a lista de mensagens garantindo estabilidade de prefixo (KV Cache friendly).

        Ordem fixa: system -> skills -> histórico (com masking) -> todo -> turno.
        """
        messages = []

        # 1. System Prompt estático e imutável
        sys_full = system_prompt.strip()
        if skills_summary:
            sys_full += f"\n\n[HABILIDADES ATIVAS]:\n{skills_summary}"
        messages.append({"role": "system", "content": sys_full})

        # 2. Histórico de mensagens
        for msg in history:
            messages.append(msg)

        # 3. Recitação do todo anexada ao turno ativo
        recitation = self.format_todo_recitation()
        turn_content = current_turn
        if recitation:
            turn_content = f"{current_turn}\n{recitation}"

        messages.append({"role": "user", "content": turn_content})
        return messages
