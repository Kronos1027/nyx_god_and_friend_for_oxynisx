from core.skills import SkillManager
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


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


def test_new_version_after_rollback_preserves_original_history(tmp_path):
    manager = SkillManager(tmp_path)
    manager.promote_task_to_skill("demo", "one", [{"value": 1}])
    manager.promote_task_to_skill("demo", "two", [{"value": 2}])
    original = (tmp_path / "demo/v2.json").read_bytes()
    assert manager.rollback("demo")
    third = manager.promote_task_to_skill("demo", "three", [{"value": 3}])
    assert third.version == 3
    assert (tmp_path / "demo/v2.json").read_bytes() == original
    assert SkillManager(tmp_path).get_skill("demo").version == 3
    assert manager.rollback("demo")
    assert manager.get_skill("demo").version == 1


def test_returned_objects_and_input_cannot_mutate_registered_steps(tmp_path):
    manager = SkillManager(tmp_path)
    steps = [{"params": {"text": "original"}}]
    created = manager.promote_task_to_skill("demo", "Example", steps)
    steps[0]["params"]["text"] = "input mutation"
    created.steps[0]["params"]["text"] = "return mutation"
    loaded = manager.get_skill("demo")
    loaded.steps.clear()
    manager.record_execution_outcome("demo", True)
    assert manager.get_skill("demo").steps == [{"params": {"text": "original"}}]


def test_multiple_managers_reload_current_version_before_writing(tmp_path):
    first, second = SkillManager(tmp_path), SkillManager(tmp_path)
    first.promote_task_to_skill("demo", "one", [{"value": 1}])
    assert second.promote_task_to_skill("demo", "two", [{"value": 2}]).version == 2
    assert first.get_skill("demo").version == 2
    second.record_execution_outcome("demo", True)
    first.record_execution_outcome("demo", True)
    assert second.get_skill("demo").success_count == 2


def test_interrupted_activation_keeps_current_and_does_not_reuse_orphan_version(tmp_path, monkeypatch):
    manager = SkillManager(tmp_path)
    manager.promote_task_to_skill("demo", "one", [{"value": 1}])
    original = (tmp_path / "demo/current.json").read_bytes()

    def fail(*_):
        raise OSError("fixture activation failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", fail)
        with pytest.raises(OSError):
            manager.promote_task_to_skill("demo", "two", [{"value": 2}])
    assert (tmp_path / "demo/current.json").read_bytes() == original
    assert manager.get_skill("demo").version == 1
    assert (tmp_path / "demo/v2.json").exists()
    assert not list((tmp_path / "demo").glob(".pending-*"))
    assert manager.promote_task_to_skill("demo", "three", [{"value": 3}]).version == 3
    assert manager.rollback("demo")
    assert manager.get_skill("demo").version == 1  # never activate the orphan v2


@pytest.mark.parametrize("name", ["", "..", "../outside", "a/b", "a\\b", "CON", "NUL", "x:y", "a" * 65])
def test_invalid_names_cannot_address_other_paths(tmp_path, name):
    manager = SkillManager(tmp_path)
    for operation in (
        lambda: manager.get_skill(name, 1), lambda: manager.rollback(name),
        lambda: manager.promote_task_to_skill(name, "invalid", [{"step": 1}]),
    ):
        with pytest.raises(ValueError):
            operation()


def test_case_collision_and_active_content_tampering_are_rejected(tmp_path):
    manager = SkillManager(tmp_path)
    manager.promote_task_to_skill("Demo", "one", [{"step": 1}])
    with pytest.raises(ValueError, match="capitalização"):
        manager.promote_task_to_skill("demo", "two", [{"step": 2}])
    path = tmp_path / "Demo/current.json"
    data = json.loads(path.read_text())
    data["steps"] = [{"unexpected": "modified"}]
    path.write_text(json.dumps(data))
    assert manager.get_skill("Demo") is None
    assert not manager.record_execution_outcome("Demo", True)


def test_exclusive_process_lease_blocks_another_writer(tmp_path):
    manager = SkillManager(tmp_path)
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    with manager._locked():
        result = subprocess.run(
            [sys.executable, "-c", "import sys; from core.skills import SkillManager; "
             "SkillManager(sys.argv[1]).promote_task_to_skill('other','Example',[{'step':1}])", str(tmp_path)],
            env=env, capture_output=True, text=True, timeout=10,
        )
    assert result.returncode != 0
    assert not (tmp_path / "other").exists()
    assert manager.promote_task_to_skill("demo", "one", [{"step": 1}]).version == 1


def test_hardlinked_active_file_does_not_receive_writes(tmp_path):
    manager = SkillManager(tmp_path / "catalog")
    manager.promote_task_to_skill("demo", "one", [{"step": 1}])
    active = manager.skills_dir / "demo/current.json"
    outside = tmp_path / "sentinel.json"
    os.link(active, outside)
    original = outside.read_bytes()
    assert not manager.record_execution_outcome("demo", True)
    assert outside.read_bytes() == original


def test_oversized_and_invalid_versions_rejected(tmp_path):
    manager = SkillManager(tmp_path)
    with pytest.raises(ValueError, match="128 KiB"):
        manager.promote_task_to_skill("demo", "large", [{"value": "x" * 131072}])
    assert not (tmp_path / "demo/v1.json").exists()
    for version in (0, 33, True, "../outside"):
        with pytest.raises(ValueError):
            manager.get_skill("demo", version)


def test_legacy_history_remains_readable_without_rewriting_archives(tmp_path):
    manager = SkillManager(tmp_path)
    manager.promote_task_to_skill("demo", "one", [{"step": 1}])
    manager.promote_task_to_skill("demo", "two", [{"step": 2}])
    for name in ("v1.json", "v2.json", "current.json"):
        path = tmp_path / "demo" / name
        data = json.loads(path.read_text())
        data.pop("previous_version")
        path.write_text(json.dumps(data))
    original = (tmp_path / "demo/v1.json").read_bytes()
    reopened = SkillManager(tmp_path)
    assert reopened.get_skill("demo").version == 2
    assert reopened.rollback("demo")
    assert reopened.get_skill("demo").version == 1
    assert (tmp_path / "demo/v1.json").read_bytes() == original
