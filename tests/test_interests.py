from core.interests import InterestEngine
from core.memory import MemoryManager


def test_inferences_and_confirmed_preferences_are_distinct_and_persist(tmp_path):
    engine = InterestEngine(tmp_path / "social.db")
    inferred = engine.remember("astronomia", kind="inferred_preference", origin="assunto recorrente", confidence=.4)
    confirmed = engine.remember("astronomia", kind="confirmed_preference", origin="usuário confirmou")
    assert inferred != confirmed
    restored = InterestEngine(engine.database)
    assert len(restored.records()) == 2
    assert "hipóteses" in restored.prompt_context()
    assert len(restored.records("confirmed_preference")) == 1


def test_interests_evolve_without_changing_security_facts(tmp_path):
    memory = MemoryManager(tmp_path)
    policy = memory.core.get("security_policy")
    for _ in range(15):
        memory.interests.remember("programação", kind="simulated_interest", origin="estudo",
                                  source="https://docs.python.org", experience="documentação lida", relevance=.8)
    records = memory.interests.records()
    assert len(records) == 1 and len(records[0]["experiences"]) == 8
    assert len(records[0]["sources"]) == 1
    assert "simulated_interest" in memory.build_system_prompt_context()
    assert memory.core.get("security_policy") == policy


def test_user_can_disable_correct_delete_and_clear_by_category(tmp_path):
    engine = InterestEngine(tmp_path / "social.db")
    identifier = engine.remember("música", kind="confirmed_preference", origin="usuário", relevance=.5)
    engine.remember("música", kind="confirmed_preference", origin="corrigido pelo usuário", relevance=.8)
    assert engine.records()[0]["relevance"] == .8
    engine.set_enabled(False)
    assert engine.remember("jogos", kind="simulated_interest", origin="estudo") is None
    assert engine.prompt_context() == ""
    engine.delete(identifier)
    engine.set_enabled(True)
    engine.remember("projeto", kind="project", origin="usuário")
    engine.remember("arte", kind="simulated_interest", origin="estudo")
    engine.clear("simulated_interest")
    assert len(engine.records()) == 1
    assert engine.records()[0]["kind"] == "project"


def test_explicit_preference_is_remembered_but_casual_topic_is_not(tmp_path):
    memory = MemoryManager(tmp_path)
    memory.record_user_message("Estamos falando de astronomia")
    assert memory.interests.records() == []
    memory.record_user_message("Lembre que gosto de astronomia.")
    assert memory.interests.records("confirmed_preference")[0]["topic"] == "astronomia"
    assert "astronomia" in MemoryManager(tmp_path).build_system_prompt_context()
