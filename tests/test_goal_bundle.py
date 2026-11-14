"""Trusted multi-file contracts: all deliverables, not the first successful tool."""
import hashlib
import json

import pytest

from audit.logger import AuditLogger
from core.agent_loop import AgentLoop
from core.goal_bundle import GoalBundle, parse_goal_contract, required_goal_tool
from core.llm_client import OfflineLLM
from core.task_journal import TaskJournal
from core.task_runner import TaskRunner
from tools.file_tool import FileTool
from tools.registry import ToolRegistry, ToolSpec


def contract(path, data):
    return {"kind": "file_sha256", "path": str(path),
            "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest()}


def bundle(*items):
    return {"kind": "file_bundle", "items": list(items)}


def step(path, *, verified=True, ok=True):
    return {"tool": "write_file", "params": {"path": str(path)},
            "verified": verified, "ok": ok}


def answer(action="none", params=None):
    return json.dumps({"emotion": "idle", "speech_output": "Entrega pronta",
                       "action": {"type": action, "params": params or {}},
                       "requires_confirmation": False})


def harness(root, messages, journal=None, auto=False):
    registry = ToolRegistry()
    filetool = FileTool([root])
    registry.register(ToolSpec("write_file", "write", sensitive=True), filetool.write_file)
    loop = AgentLoop(OfflineLLM(messages), registry, AuditLogger(root / "logs"))
    runner = TaskRunner(loop, journal=journal, acceptance_roots=[root])
    if auto:
        runner.set_budget_profile("default")
    return runner, loop


def test_partial_delivery_cannot_claim_full_project(tmp_path):
    a, b, c = [tmp_path / item for item in ("app.py", "tests.py", "settings.json")]
    expected = bundle(contract(a, "code"), contract(b, "test"), contract(c, "{}"))
    goal = parse_goal_contract(expected, [tmp_path])
    assert goal.kind == "file_bundle"
    assert required_goal_tool(goal) == "write_file"
    a.write_text("code")
    b.write_text("test")
    assert goal.evaluate([step(a), step(b)], [tmp_path]).reason == "verified_2_of_3"
    c.write_text("{}")
    assert goal.evaluate([step(a), step(b), step(c, verified=False)], [tmp_path]).reason == "verified_2_of_3"
    assert goal.evaluate([step(a), step(b), step(c)], [tmp_path]).passed


def test_bundle_round_trip_and_revalidation(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    spec = bundle(contract(a, "a"), contract(b, "b"))
    goal = GoalBundle.parse(spec, [tmp_path])
    assert GoalBundle.parse(goal.as_dict(), [tmp_path]) == goal
    a.write_text("a")
    b.write_text("b")
    assert goal.evaluate([step(a), step(b)], [tmp_path]).passed
    b.write_text("TAMPERED")
    assert goal.evaluate([step(a), step(b)], [tmp_path]).reason == "verified_1_of_2"


@pytest.mark.parametrize("bad", [
    {"kind": "file_bundle", "items": []},
    {"kind": "file_bundle", "items": "not list"},
    {"kind": "file_bundle", "items": [{}]},
    {"kind": "file_bundle", "items": [{"kind": "shell"}] * 2},
    {"kind": "file_bundle", "items": [], "hidden": True},
])
def test_bundle_rejects_incomplete_untrusted_contract(tmp_path, bad):
    with pytest.raises(ValueError):
        GoalBundle.parse(bad, [tmp_path])


def test_bundle_rejects_duplicates_and_outside_root(tmp_path):
    a, b = tmp_path / "same", tmp_path.parent / "outside"
    with pytest.raises(ValueError, match="duplicados"):
        GoalBundle.parse(bundle(contract(a, "a"), contract(a, "b")), [tmp_path])
    with pytest.raises(ValueError, match="fora"):
        GoalBundle.parse(bundle(contract(a, "a"), contract(b, "b")), [tmp_path])


def test_eight_is_hard_limit_and_nested_contracts_are_rejected(tmp_path):
    entries = [contract(tmp_path / f"{n}.txt", str(n)) for n in range(9)]
    assert len(GoalBundle.parse(bundle(*entries[:8]), [tmp_path]).items) == 8
    with pytest.raises(ValueError):
        GoalBundle.parse(bundle(*entries), [tmp_path])
    with pytest.raises(ValueError):
        GoalBundle.parse(bundle(bundle(entries[0], entries[1]), entries[2]), [tmp_path])


def test_runner_requires_both_approved_files(tmp_path):
    a, b = tmp_path / "app.txt", tmp_path / "tests.txt"
    runner, _ = harness(tmp_path, [
        answer("write_file", {"path": str(a), "content": "app"}),
        answer("write_file", {"path": str(b), "content": "tests"}),
        answer(),
    ])
    spec = bundle(contract(a, "app"), contract(b, "tests"))
    first = runner.start("Crie o aplicativo e os testes", acceptance=spec)
    assert first.needs_confirmation and not a.exists() and not b.exists()
    second = runner.resume(first.pending_action, True)
    assert second.needs_confirmation and a.exists() and not b.exists()
    last = runner.resume(second.pending_action, True)
    assert runner.goal_verdict == {
        "status": "VERIFIED", "reason": "all_files_verified", "kind": "file_bundle",
    }
    assert "NÃO verificada" not in last.response.speech_output


def test_one_file_never_satisfies_two_file_task(tmp_path):
    a, b = tmp_path / "app.txt", tmp_path / "tests.txt"
    runner, _ = harness(tmp_path, [
        answer("write_file", {"path": str(a), "content": "app"}),
        answer(),
    ])
    first = runner.start("Crie aplicativo e testes",
                         acceptance=bundle(contract(a, "app"), contract(b, "tests")))
    final = runner.resume(first.pending_action, True)
    assert runner.goal_verdict["reason"] == "verified_1_of_2"
    assert "NÃO verificada" in final.response.speech_output


def test_bundle_automated_replan_remains_one_and_never_auto_writes(tmp_path):
    a, b = tmp_path / "app", tmp_path / "test"
    runner, llm = harness(tmp_path, [answer(), answer()], auto=True)
    final = runner.start("Crie app e testes",
                         acceptance=bundle(contract(a, "code"), contract(b, "test")))
    assert runner.goal_attempts == 1
    assert len(llm.llm.received) == 2
    assert "NÃO verificada" in final.response.speech_output
    assert not a.exists() and not b.exists()


def test_restart_keeps_all_bundle_goals(tmp_path):
    a, b = tmp_path / "app", tmp_path / "tests"
    journal = TaskJournal(tmp_path / "journal.db")
    runner, loop = harness(tmp_path, [], journal=journal)

    class Pause:
        def generate(self, prompt, **kwargs):
            runner.pause()
            return answer()

    loop.llm = Pause()
    runner.start("Crie app e testes",
                 acceptance=bundle(contract(a, "one"), contract(b, "two")))
    task_id = runner.task_id
    assert journal.get(task_id)["state"] == "PAUSED"
    assert len(journal.get(task_id)["goal_contract"]["items"]) == 2
    journal.close()

    new_journal = TaskJournal(tmp_path / "journal.db")
    resumed, _ = harness(tmp_path, [answer()], journal=new_journal)
    final = resumed.continue_task(task_id)
    assert resumed.goal_contract.kind == "file_bundle"
    assert resumed.goal_verdict["reason"] == "verified_0_of_2"
    assert "NÃO verificada" in final.response.speech_output
    new_journal.close()
