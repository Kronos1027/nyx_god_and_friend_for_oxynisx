"""Testes do sistema de memória avançada (EpisodicStore, CoreMemory, ContextCompactor, MemoryManager)."""

from core.memory import MemoryManager


def test_episodic_store_and_core_memory(tmp_path):
    mgr = MemoryManager(data_dir=tmp_path, session_id="test_sess")

    # Verifica fatos padrão
    core = mgr.core.all()
    assert "system_os" in core
    assert "hardware_gpu" in core

    # Gravação e recuperação de fato
    mgr.core.set("user_name", "Darlan", category="user_profile")
    assert mgr.core.get("user_name") == "Darlan"

    # Aprendizado automático por heurística de texto
    mgr.record_user_message("Olá, me chamo Darlan e estou trabalhando no projeto nyx-agent")
    assert mgr.core.get("user_name") == "Darlan"
    assert mgr.core.get("active_project") == "nyx-agent"

    # Grava resposta do assistente
    mgr.record_assistant_message("Prazer, Darlan. Como posso ajudar?", action_type="none")

    # Recupera histórico
    history = mgr.get_recent_history(limit=5)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    # Busca em memórias passadas
    results = mgr.search_memories("nyx-agent")
    assert len(results) >= 1
    assert "nyx-agent" in results[0]["content"]

    # Persistência entre reinicializações
    mgr2 = MemoryManager(data_dir=tmp_path, session_id="test_sess")
    assert mgr2.core.get("user_name") == "Darlan"
    assert mgr2.core.get("active_project") == "nyx-agent"
    assert len(mgr2.get_recent_history(limit=5)) == 2


def test_context_compactor(tmp_path):
    mgr = MemoryManager(data_dir=tmp_path, session_id="compact_sess")

    # Insere 15 turnos
    for i in range(15):
        mgr.record_user_message(f"Passo {i}: faça isso")
        mgr.record_assistant_message(f"Concluí passo {i}", action_type="shell")

    history = mgr.get_recent_history(limit=30)
    assert len(history) == 30

    summary, recent = mgr.compactor.compact(history)
    assert summary is not None
    assert "Resumo dos passos anteriores" in summary
    assert len(recent) == mgr.compactor.max_recent_turns
