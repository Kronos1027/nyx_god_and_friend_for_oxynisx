"""End-to-end runtime postconditions with normal tool permissions and journal."""
import hashlib
import json

import pytest

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_journal import TaskJournal
from core.task_runner import TaskRunner
from tools.file_tool import FileTool
from tools.registry import ToolRegistry, ToolSpec


def reply(tool="none", params=None, speech="Pronto"):
    return json.dumps({"emotion": "idle", "action": {"type": tool, "params": params or {}},
                       "requires_confirmation": False, "speech_output": speech})


def acceptance(path, text):
    return {"kind": "file_sha256", "path": str(path),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def build(tmp_path, responses, *, journal=None, auto=False):
    registry = ToolRegistry()
    loop = AgentLoop(OfflineLLM(responses), registry, AuditLogger(tmp_path / "logs"))
    runner = TaskRunner(loop, journal=journal, acceptance_roots=[tmp_path])
    if auto:
        runner.set_budget_profile("default")
    filetool = FileTool([tmp_path])
    registry.register(ToolSpec("write_file", "write file", sensitive=True),
                      filetool.write_file)
    return runner, loop


def test_verified_write_satisfies_goal_not_merely_tool_return(tmp_path):
    path = tmp_path / "answer.txt"
    wanted = "exact answer\n"
    runner, _ = build(tmp_path, [
        reply("write_file", {"path": str(path), "content": wanted}),
        reply(speech="Arquivo pronto"),
    ])
    pending = runner.start("Grave o arquivo", acceptance=acceptance(path, wanted))
    assert pending.needs_confirmation and not path.exists()
    result = runner.resume(pending.pending_action, True)
    assert path.read_text() == wanted
    assert runner.goal_verdict == {"status": "VERIFIED", "reason": "exact_sha256",
                                   "kind": "file_sha256"}
    assert "NÃO verificada" not in result.response.speech_output


def test_wrong_written_content_never_counts_as_goal_done(tmp_path):
    path = tmp_path / "wrong.txt"
    runner, _ = build(tmp_path, [
        reply("write_file", {"path": str(path), "content": "wrong"}),
        reply(speech="Concluído"),
    ])
    pending = runner.start("Grave o arquivo", acceptance=acceptance(path, "correct"))
    result = runner.resume(pending.pending_action, True)
    assert runner.steps[0]["verified"] is True  # tool succeeded!
    assert runner.goal_verdict["reason"] == "hash_mismatch"
    assert "NÃO verificada" in result.response.speech_output


def test_preexisting_file_does_not_fake_completion(tmp_path):
    path = tmp_path / "existing.txt"
    path.write_text("old")
    runner, _ = build(tmp_path, [reply(speech="Gravado")])
    result = runner.start("Grave o arquivo", acceptance=acceptance(path, "old"))
    assert runner.goal_verdict["reason"] == "no_verified_write"
    assert "NÃO verificada" in result.response.speech_output
    assert runner.steps == []


def test_one_additional_replan_when_explicit_goal_remains_open(tmp_path):
    path = tmp_path / "missing.txt"
    runner, loop = build(tmp_path, [reply(), reply()], auto=True)
    result = runner.start("Grave o arquivo", acceptance=acceptance(path, "expected"))
    assert runner.goal_attempts == 1
    assert len(loop.llm.received) == 2
    assert "pós-condição declarada" in loop.llm.received[1]
    assert "NÃO verificada" in result.response.speech_output
    events = [e for e in loop.audit.read_all() if e["event"] == "task_replan"]
    assert any(e["reason"] == "goal_postcondition_unverified" for e in events)


def test_bad_contract_rejected_before_task_becomes_active(tmp_path):
    runner, _ = build(tmp_path, [reply()])
    with pytest.raises(ValueError):
        runner.start("Grave", acceptance={
            "kind": "file_sha256", "path": str(tmp_path.parent / "secret"),
            "sha256": "a" * 64,
        })
    assert not runner.active
    assert runner.steps == []


def test_declined_confirmation_never_claims_goal_satisfied(tmp_path):
    path = tmp_path / "no.txt"
    runner, _ = build(tmp_path, [reply("write_file", {"path": str(path), "content": "ok"})])
    pending = runner.start("Grave arquivo", acceptance=acceptance(path, "ok"))
    result = runner.resume(pending.pending_action, False)
    assert not path.exists()
    assert runner.goal_verdict["reason"] == "no_verified_write"
    assert "NÃO verificada" in result.response.speech_output


def test_contract_persists_across_pause_and_restart(tmp_path):
    path = tmp_path / "note.txt"
    journal_path = tmp_path / "tasks.db"
    journal = TaskJournal(journal_path)
    runner, loop = build(tmp_path, [], journal=journal)

    class Pausing:
        def generate(self, prompt, **kwargs):
            runner.pause()
            return reply()
    loop.llm = Pausing()
    runner.start("Grave arquivo", acceptance=acceptance(path, "ok"))
    task_id = runner.task_id
    saved = journal.get(task_id)
    assert saved["state"] == "PAUSED"
    assert saved["goal_contract"]["kind"] == "file_sha256"
    journal.close()

    journal = TaskJournal(journal_path)
    resumed, _ = build(tmp_path, [reply()], journal=journal)
    result = resumed.continue_task(task_id)
    assert resumed.goal_contract is not None
    assert resumed.goal_verdict["reason"] == "no_verified_write"
    assert "NÃO verificada" in result.response.speech_output
    journal.close()


def test_model_cannot_invoke_unexposed_delete_action(tmp_path):
    """An optional absence contract must not grant a tool permission."""
    path = tmp_path / "obsolete.txt"
    path.write_text("must not remove")
    runner, _ = build(tmp_path, [
        reply("delete_file", {"path": str(path)}),
    ])
    filetool = FileTool([tmp_path])
    runner.loop.registry.register(ToolSpec("delete_file", "delete file", destructive=True),
                                  filetool.delete_file)
    result = runner.start("Exclua o arquivo", acceptance={
        "kind": "file_absent", "path": str(path),
    })
    assert not result.needs_confirmation
    assert not result.executed
    assert path.read_text() == "must not remove"
    assert runner.goal_verdict["status"] == "UNVERIFIED"
    assert runner.goal_verdict["reason"] == "no_verified_delete"
    assert "NÃO verificada" in result.response.speech_output


def test_previously_absent_file_is_not_evidence_of_deletion(tmp_path):
    path = tmp_path / "already_missing"
    runner, _ = build(tmp_path, [reply(speech="Já removido")])
    answer = runner.start("Exclua o arquivo", acceptance={
        "kind": "file_absent", "path": str(path),
    })
    assert runner.goal_verdict["reason"] == "no_verified_delete"
    assert "NÃO verificada" in answer.response.speech_output
