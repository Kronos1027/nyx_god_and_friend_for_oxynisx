from core.skills import SkillManager


def test_skill_lifecycle_and_rollback(tmp_path):
    mgr = SkillManager(skills_dir=tmp_path)

    # 1. Promove tarefa a Skill v1
    steps_v1 = [{"type": "shell", "params": {"cmd": "echo v1"}}]
    s1 = mgr.promote_task_to_skill("limpar_temporarios", "Limpa cache e temp", steps_v1)
    assert s1.version == 1
    assert mgr.get_skill("limpar_temporarios").version == 1

    # 2. Atualiza para Skill v2
    steps_v2 = [{"type": "shell", "params": {"cmd": "echo v2_otimizada"}}]
    s2 = mgr.promote_task_to_skill("limpar_temporarios", "Limpa cache otimizado", steps_v2)
    assert s2.version == 2
    assert mgr.get_skill("limpar_temporarios").version == 2

    # 3. Simula falhas consecutivas da v2 em produção
    mgr.record_execution_outcome("limpar_temporarios", success=False)
    # Ainda em v2 após 1 falha
    assert mgr.get_skill("limpar_temporarios").version == 2

    # Segunda falha consecutiva dispara o auto-rollback para v1!
    mgr.record_execution_outcome("limpar_temporarios", success=False)
    rolled_back = mgr.get_skill("limpar_temporarios")
    assert rolled_back.version == 1
    assert rolled_back.steps == steps_v1


def test_list_skills(tmp_path):
    mgr = SkillManager(skills_dir=tmp_path)
    mgr.promote_task_to_skill("tarefa_a", "Desc A", [{"step": 1}])
    mgr.promote_task_to_skill("tarefa_b", "Desc B", [{"step": 1}, {"step": 2}])

    skills = mgr.list_skills()
    assert len(skills) == 2
    names = {s["name"] for s in skills}
    assert names == {"tarefa_a", "tarefa_b"}
