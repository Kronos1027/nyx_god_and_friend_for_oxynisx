"""Nyx — core/memory.py (Arquitetura de Memória Avançada de Longo Prazo)

Implementa uma arquitetura de memória em 3 camadas inspirada em MemGPT e Mem0:
1. Core Memory (Fatos-chave, perfil e preferências injetados no system prompt)
2. Episodic Store (SQLite local com FTS5 para persistência imutável entre sessões)
3. Context Compactor (Janela deslizante com sumarização progressiva para tarefas longas)
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CORE_FACTS = {
    "system_os": "Windows 11",
    "hardware_gpu": "NVIDIA GeForce RTX 3060 (12GB VRAM)",
    "nyx_persona": "Nyx: IA desktop kuudere, perspicaz, protetora e direta. Viseira verde (assistida) / ambar (autonoma).",
    "security_policy": "Acoes destrutivas sempre exigem confirmacao humana explicita via dialog.",
}


@dataclass
class ConversationRecord:
    session_id: str
    role: str
    content: str
    action_type: str = "none"
    action_params: dict = field(default_factory=dict)
    tool_result: str | None = None
    emotion: str = "idle"
    timestamp: str = ""


class EpisodicStore:
    """Armazenamento relacional persistente em SQLite local com busca FTS5."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    action_type TEXT DEFAULT 'none',
                    action_params TEXT DEFAULT '{}',
                    tool_result TEXT,
                    emotion TEXT DEFAULT 'idle',
                    created_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    updated_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS task_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    turn_start INTEGER NOT NULL,
                    turn_end INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Tabela virtual FTS5 para busca textual ultra-rápida
            try:
                cur.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
                        content,
                        session_id,
                        role,
                        content='conversations',
                        content_rowid='id'
                    )
                    """
                )
            except Exception as e:
                log.warning(f"FTS5 não disponível no SQLite do sistema: {e}")
            conn.commit()

    def save_turn(self, record: ConversationRecord) -> int:
        ts = record.timestamp or datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO conversations (
                    session_id, role, content, action_type, action_params,
                    tool_result, emotion, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.session_id,
                    record.role,
                    record.content,
                    record.action_type,
                    json.dumps(record.action_params, ensure_ascii=False),
                    record.tool_result,
                    record.emotion,
                    ts,
                ),
            )
            row_id = cur.lastrowid
            # Atualiza FTS5 se tabela existir
            try:
                cur.execute(
                    """
                    INSERT INTO conversations_fts (rowid, content, session_id, role)
                    VALUES (?, ?, ?, ?)
                    """,
                    (row_id, record.content, record.session_id, record.role),
                )
            except Exception:
                pass
            conn.commit()
            return row_id

    def get_recent_history(self, session_id: str, limit: int = 12) -> list[dict]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT role, content, action_type, action_params, tool_result, emotion
                FROM conversations
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (session_id, limit),
            )
            rows = cur.fetchall()
            result = []
            for r in reversed(rows):
                result.append({
                    "role": r["role"],
                    "content": r["content"],
                    "action_type": r["action_type"],
                    "action_params": json.loads(r["action_params"] or "{}"),
                    "tool_result": r["tool_result"],
                    "emotion": r["emotion"],
                })
            return result

    def set_fact(self, key: str, value: str, category: str = "general") -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO facts (key, value, category, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    updated_at = excluded.updated_at
                """,
                (key, value, category, ts),
            )
            conn.commit()

    def get_all_facts(self) -> dict[str, str]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM facts ORDER BY key")
            return {r["key"]: r["value"] for r in cur.fetchall()}

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Busca em memórias passadas via FTS5 com fallback para LIKE."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            results = []
            try:
                # FTS5 com termos separados por espaço ou asterisco
                terms = [re.sub(r"[^\w]", "", t) for t in query.split() if re.sub(r"[^\w]", "", t)]
                if terms:
                    fts_query = " OR ".join(terms)
                    cur.execute(
                        """
                        SELECT c.id, c.session_id, c.role, c.content, c.created_at
                        FROM conversations c
                        JOIN conversations_fts f ON c.id = f.rowid
                        WHERE conversations_fts MATCH ?
                        ORDER BY c.id DESC LIMIT ?
                        """,
                        (fts_query, limit),
                    )
                    results = [dict(r) for r in cur.fetchall()]
            except Exception:
                results = []

            if not results:
                cur.execute(
                    """
                    SELECT id, session_id, role, content, created_at
                    FROM conversations
                    WHERE content LIKE ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (f"%{query}%", limit),
                )
                results = [dict(r) for r in cur.fetchall()]

            return results


class CoreMemory:
    """Gerencia fatos duradouros da memória do agente e perfil do usuário."""

    def __init__(self, store: EpisodicStore) -> None:
        self.store = store
        self._facts: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        stored = self.store.get_all_facts()
        if not stored:
            for k, v in DEFAULT_CORE_FACTS.items():
                self.store.set_fact(k, v, category="system")
            stored = self.store.get_all_facts()
        self._facts = stored

    def set(self, key: str, value: str, category: str = "general") -> None:
        self._facts[key] = value
        self.store.set_fact(key, value, category)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._facts.get(key, default)

    def all(self) -> dict[str, str]:
        return dict(self._facts)

    def learn_from_text(self, text: str) -> list[tuple[str, str]]:
        """Extrai automaticamente fatos óbvios mencionados pelo usuário."""
        learned = []
        m = re.search(r"(?:me chamo|meu nome [ée])\s+([A-ZÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ][\wÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇa-záàâãéèêíïóôõöúç]+)", text, re.I)
        if m:
            name = m.group(1).strip()
            self.set("user_name", name, category="user_profile")
            learned.append(("user_name", name))

        m_remember = re.search(r"(?:lembre-se\s+(?:de\s+que|que)|guarde\s+que)\s+(.+)", text, re.I)
        if m_remember:
            fact = m_remember.group(1).strip()
            key = f"note_{datetime.now(timezone.utc).strftime('%m%d_%H%M%S')}"
            self.set(key, fact, category="user_notes")
            learned.append((key, fact))

        m_proj = re.search(r"(?:meu projeto [ée]|projeto|trabalhando no projeto)\s+([\w\-_]+)", text, re.I)
        if m_proj:
            proj = m_proj.group(1).strip()
            self.set("active_project", proj, category="projects")
            learned.append(("active_project", proj))

        return learned

    def format_prompt_block(self) -> str:
        """Gera o bloco compacto injetado no system prompt."""
        lines = ["[MEMÓRIA DE LONGO PRAZO / CORE FACTS]"]
        for k, v in sorted(self._facts.items()):
            lines.append(f"- {k}: {v}")
        return "\n".join(lines)


class ContextCompactor:
    """Mantém tarefas longas sob controle resumindo o histórico antigo sem perder o fio."""

    def __init__(self, max_recent_turns: int = 10) -> None:
        self.max_recent_turns = max_recent_turns
        self.task_summary: str | None = None

    def compact(self, history: list[dict]) -> tuple[str | None, list[dict]]:
        """Devolve (sumario_de_contexto_anterior, turnos_recentes)."""
        if len(history) <= self.max_recent_turns:
            return self.task_summary, history

        older = history[:-self.max_recent_turns]
        recent = history[-self.max_recent_turns:]

        summary_lines = []
        for h in older:
            role = "Usuário" if h.get("role") == "user" else "Nyx"
            content = h.get("content", "").replace("\n", " ")
            if len(content) > 100:
                content = content[:97] + "..."
            action = h.get("action_type")
            if action and action != "none":
                summary_lines.append(f"{role}: {content} [Ação: {action}]")
            else:
                summary_lines.append(f"{role}: {content}")

        new_summary = "Resumo dos passos anteriores da conversa/tarefa:\n" + "\n".join(summary_lines[-8:])
        self.task_summary = new_summary
        return self.task_summary, recent


class MemoryManager:
    """Ponto de entrada unificado para o AgentLoop."""

    def __init__(self, data_dir: Path, session_id: str = "main") -> None:
        self.data_dir = Path(data_dir)
        self.session_id = session_id
        self.db_path = self.data_dir / "nyx_memory.db"
        self.store = EpisodicStore(self.db_path)
        self.core = CoreMemory(self.store)
        self.compactor = ContextCompactor(max_recent_turns=10)

    def record_user_message(self, text: str) -> None:
        self.core.learn_from_text(text)
        self.store.save_turn(
            ConversationRecord(
                session_id=self.session_id,
                role="user",
                content=text,
            )
        )

    def record_assistant_message(
        self,
        content: str,
        action_type: str = "none",
        action_params: dict | None = None,
        tool_result: str | None = None,
        emotion: str = "idle",
    ) -> None:
        self.store.save_turn(
            ConversationRecord(
                session_id=self.session_id,
                role="assistant",
                content=content,
                action_type=action_type,
                action_params=action_params or {},
                tool_result=tool_result,
                emotion=emotion,
            )
        )

    def get_recent_history(self, limit: int = 12) -> list[dict]:
        return self.store.get_recent_history(self.session_id, limit=limit)

    def build_system_prompt_context(self) -> str:
        """Gera o contexto de memória para acoplar ao System Prompt."""
        parts = [self.core.format_prompt_block()]
        if self.compactor.task_summary:
            parts.append(f"\n[CONTEXTO DE TAREFA / RESUMO PROGRESSIVO]\n{self.compactor.task_summary}")
        return "\n\n".join(parts)

    def search_memories(self, query: str, limit: int = 5) -> list[dict]:
        return self.store.search(query, limit=limit)
