import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_journal import TaskJournal
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def reply(tool="none", params=None):
    return json.dumps({"emotion": "idle", "action": {"type": tool, "params": params or {}},
                       "speech_output": "Resultado consultado", "requires_confirmation": False})


def runner_at(root, journal, replies, **kwargs):
    registry = ToolRegistry()
    loop = AgentLoop(OfflineLLM(replies), registry, AuditLogger(root / "logs"))
    registry.register(ToolSpec("read_file", "Read owned files"),
                      lambda p: ToolResult(True, Path(p["path"]).read_text()))
    return TaskRunner(loop, journal=journal, **kwargs), registry


def test_eight_real_reads_pause_restart_and_continue_same_id(tmp_path):
    paths = [tmp_path / f"value-{i}.txt" for i in range(8)]
    for i, path in enumerate(paths):
        path.write_text(str(10+i))
    replies = [reply("read_file", {"path": str(p)}) for p in paths]
    journal = TaskJournal(tmp_path / "tasks.db")
    runner, _ = runner_at(tmp_path, journal, replies[:4], max_actions=12, timeout=600)
    def progress(event):
        if event["phase"] == "observed" and event["step"] == 4:
            runner.pause()
    runner.start("Leia os oito valores", progress)
    identity = runner.task_id
    first = journal.get(identity)
    assert first["state"] == "PAUSED" and len(first["steps"]) == 4
    journal.close()
    journal = TaskJournal(tmp_path / "tasks.db")
    try:
        restored, _ = runner_at(tmp_path, journal, replies[4:] + [reply()])
        restored.continue_task(identity)
        saved = journal.get(identity)
        assert saved["id"] == identity and saved["state"] == "PLANNING_FINISHED"
        assert [step["output"] for step in saved["steps"]] == [str(10+i) for i in range(8)]
        assert saved["spent"] >= first["spent"]
        assert saved["max_actions"] == 12 and saved["timeout"] == 600
        assert all(step["verified"] for step in saved["steps"])
    finally:
        journal.close()


def test_automatic_continuation_survives_pause_at_six_and_restart(tmp_path):
    paths = [tmp_path / f"value-{i}.txt" for i in range(8)]
    for i, path in enumerate(paths):
        path.write_text(str(i))
    actions = [reply("read_file", {"path": str(path)}) for path in paths]
    journal = TaskJournal(tmp_path / "tasks.db")
    runner, _ = runner_at(tmp_path, journal, actions[:6])
    runner.set_budget_profile("default")
    def progress(event):
        if event["phase"] == "observed" and event["step"] == 6:
            runner.pause()
    runner.start("Leia os oito valores", progress)
    identity = runner.task_id
    assert journal.get(identity)["auto_extend"] is True
    journal.close()
    journal = TaskJournal(tmp_path / "tasks.db")
    try:
        restored, _ = runner_at(tmp_path, journal, actions[6:] + [reply()])
        restored.continue_task(identity)
        saved = journal.get(identity)
        assert saved["state"] == "PLANNING_FINISHED" and len(saved["steps"]) == 8
        assert saved["max_actions"] == 12 and saved["timeout"] == 1800
    finally:
        journal.close()


def test_real_process_crash_after_effect_never_replays(tmp_path):
    helper = tmp_path / "trusted_crash_test.py"
    helper.write_text('''import json,os,sys
from pathlib import Path
from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_journal import TaskJournal
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry,ToolSpec
root=Path(sys.argv[1])
registry=ToolRegistry()
def effect(params):
    (root/'effect.txt').write_text('one effect')
    os._exit(7)
registry.register(ToolSpec('write_file','owned fixture'),effect)
raw=json.dumps({'emotion':'idle','action':{'type':'write_file','params':{'path':str(root/'effect.txt'),'content':'one effect'}},'speech_output':'working','requires_confirmation':False})
runner=TaskRunner(AgentLoop(OfflineLLM([raw]),registry,AuditLogger(root/'logs')),journal=TaskJournal(root/'tasks.db'))
runner.start('Crie o arquivo uma vez')
''', encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    process = subprocess.run([sys.executable, str(helper), str(tmp_path)], env=env,
                             capture_output=True, timeout=10)
    assert process.returncode == 7, process.stderr
    assert (tmp_path / "effect.txt").read_text() == "one effect"
    journal = TaskJournal(tmp_path / "tasks.db")
    try:
        task = journal.list()[0]
        assert task["state"] == "WAITING_REVIEW" and task["inflight"] == "write_file"
        runner, registry = runner_at(tmp_path, journal, [])
        registry.register(ToolSpec("write_file", "must not replay"), lambda p: pytest.fail("replay"))
        with pytest.raises(ValueError, match="incerto"):
            runner.continue_task(task["id"])
        assert not runner.active
        assert (tmp_path / "effect.txt").read_text() == "one effect"
    finally:
        journal.close()


def test_approval_does_not_survive_restart(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.db")
    action = reply("write_file", {"path": str(tmp_path / "x"), "content": "x"})
    runner, registry = runner_at(tmp_path, journal, [action])
    registry.register(ToolSpec("write_file", "sensitive", sensitive=True), lambda p: pytest.fail("unapproved"))
    pending = runner.start("Escreva")
    assert pending.needs_confirmation
    identity = runner.task_id
    journal.close()
    journal = TaskJournal(tmp_path / "tasks.db")
    try:
        restored, registry = runner_at(tmp_path, journal, [action])
        registry.register(ToolSpec("write_file", "sensitive", sensitive=True), lambda p: pytest.fail("old approval"))
        assert journal.get(identity)["pending"] is None
        with pytest.raises(ValueError):
            restored.resume(pending.pending_action, True)
        result = restored.continue_task(identity)
        assert result.needs_confirmation
    finally:
        journal.close()


def test_journal_write_failure_prevents_effect(tmp_path, monkeypatch):
    journal = TaskJournal(tmp_path / "tasks.db")
    runner, registry = runner_at(tmp_path, journal, [reply("find_files", {"path": "x"})])
    registry.register(ToolSpec("find_files", "must not run"), lambda p: pytest.fail("effect without intent"))
    save = journal.save
    def fail_intent(item):
        if item["state"] == "ACT":
            raise OSError("disk full")
        save(item)
    monkeypatch.setattr(journal, "save", fail_intent)
    try:
        result = runner.start("Leia")
        assert "disk full" in result.response.speech_output
        assert not runner.active
    finally:
        journal.close()


def test_exclusive_journal_redaction_and_bounded_pending_retention(tmp_path):
    journal = TaskJournal(tmp_path / "tasks.db")
    try:
        with pytest.raises(RuntimeError, match="Outro runtime"):
            TaskJournal(tmp_path / "tasks.db")
        journal.LIMIT = 2
        for i in range(2):
            journal.save({"id": str(i), "state": "PAUSED", "goal": "senha=hidden",
                          "pending": {"api_key": "hidden"}})
        assert "hidden" not in json.dumps(journal.list())
        assert all(t["redacted"] for t in journal.list())
        with pytest.raises(ValueError, match="cheio"):
            journal.save({"id": "third", "state": "PLAN"})
        journal.delete("0")
        assert len(journal.list()) == 1
    finally:
        journal.close()


def test_team_pressure_and_subtask_states_survive_in_parent_checkpoint(tmp_path):
    from core.agent_team import make_agent_team_tool_func
    from core.runtime_budget import InferencePressureError
    journal = TaskJournal(tmp_path / "tasks.db")
    runner, registry = runner_at(tmp_path, journal, [])
    class Model:
        calls = 0
        def generate(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return reply("agent_team", {"tasks": [{"id": "read", "role": "arquivos", "task": "Leia"}]})
            if self.calls == 2:
                raise InferencePressureError("Memória reservada")
            return reply()
    runner.loop.llm = model = Model()
    registry.register(ToolSpec("agent_team", "delegation"),
                      make_agent_team_tool_func(model, registry, runner.loop.audit))
    try:
        runner.start("Investigue")
        saved = journal.get(runner.task_id)
        assert saved["state"] == "RESOURCE_PRESSURE"
        assert saved["steps"][0]["subtasks"][0]["state"] == "RESOURCE_PRESSURE"
        assert not runner.active
        runner.continue_task(runner.task_id)
        assert journal.get(runner.task_id)["state"] == "PLANNING_FINISHED"
        assert len(runner.steps) == 1  # no automatic repeat of the prior delegation
    finally:
        journal.close()


def test_direct_inference_pressure_is_resumable_without_new_budget(tmp_path):
    from core.runtime_budget import InferencePressureError
    journal = TaskJournal(tmp_path / "tasks.db")
    runner, _ = runner_at(tmp_path, journal, [])
    def pressure(*args, **kwargs):
        raise InferencePressureError("RAM livre insuficiente")
    runner.loop.llm.generate = pressure
    try:
        runner.start("Leia depois")
        saved = journal.get(runner.task_id)
        assert saved["state"] == "RESOURCE_PRESSURE" and not saved["steps"]
        runner.loop.llm = OfflineLLM([reply()])
        runner.continue_task(runner.task_id)
        assert journal.get(runner.task_id)["timeout"] == saved["timeout"]
    finally:
        journal.close()
