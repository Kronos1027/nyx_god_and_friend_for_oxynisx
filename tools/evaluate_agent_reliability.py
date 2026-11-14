"""Reproducible agent reliability smoke suite (scripted model, real agent runner).

Does NOT measure a local LLM's ability, GPU latency or Windows UI acceptance.
Runs only temporary file operations and read-only delegates. No external URLs.
Usage: python tools/evaluate_agent_reliability.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from audit.logger import AuditLogger  # noqa: E402
from core.agent_loop import AgentLoop  # noqa: E402
from core.agent_team import AgentTeam  # noqa: E402
from core.llm_client import OfflineLLM  # noqa: E402
from core.task_reliability import StepEvidence  # noqa: E402
from core.task_runner import TaskRunner  # noqa: E402
from tools.registry import ToolRegistry, ToolResult, ToolSpec  # noqa: E402
from tools.file_tool import FileTool  # noqa: E402


def answer(tool="none", params=None, speech="Conclusão"):
    return json.dumps({"emotion": "idle", "speech_output": speech,
                       "action": {"type": tool, "params": params or {}},
                       "requires_confirmation": False}, ensure_ascii=False)


def prepare(root, replies, *, acceptance_roots=()):
    registry = ToolRegistry()
    llm = OfflineLLM(replies)
    loop = AgentLoop(llm, registry, AuditLogger(root / "logs"))
    return TaskRunner(loop, acceptance_roots=acceptance_roots), registry, llm, loop


def evaluate(root: Path) -> list[dict]:
    checks = []

    def record(name, accepted, **metrics):
        checks.append({"scenario": name, "passed": bool(accepted), **metrics})

    # Scenario 1: eight independent, physically read text files; bounded extension.
    eight = root / "eight"
    eight.mkdir()
    paths = []
    for i in range(8):
        p = eight / f"step{i}.txt"
        p.write_text(f"message-{i}", encoding="utf-8")
        paths.append(p)
    responses = [answer("read_file", {"path": str(p)}) for p in paths] + [answer(speech="Oito leituras")]
    runner, registry, _, _ = prepare(root / "case8", responses)
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, Path(p["path"]).read_text(encoding="utf-8")))
    runner.set_budget_profile("default")
    final = runner.start("Leia oito arquivos")
    ev = StepEvidence.inspect(runner.steps)
    record("eight_verified_reads", ev.verified == 8 and len(runner.steps) == 8 and
           final.response.speech_output == "Oito leituras" and runner.max_actions == 12,
           verified=ev.verified, actions=len(runner.steps))

    # Scenario 2: model claims it opened an application without actions; no false completion.
    runner, registry, _, _ = prepare(root / "case-nothing", [answer(), answer()])
    registry.register(ToolSpec("ui_action", "read-only dummy for planner"), lambda p: ToolResult(True, "not used"))
    runner.set_budget_profile("default")
    final = runner.start("Abra um aplicativo")
    record("unverified_claim", runner.delivery_replans == 1 and runner.steps == [] and
           "não foi comprovada" in final.response.speech_output,
           delivery_replans=runner.delivery_replans)

    # Scenario 3: failed reading yields safe feedback and fallback tool.
    runner, registry, model, _ = prepare(root / "case-recover", [
        answer("read_file", {"path": "/missing"}),
        answer("find_files", {"pattern": "*.txt"}),
        answer(speech="Arquivo não encontrado; lista revisada"),
    ])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(False, error="not found"))
    registry.register(ToolSpec("find_files", "lookup"), lambda p: ToolResult(True, "Nenhum arquivo"))
    final = runner.start("Encontre o arquivo para ler")
    record("safe_replan_after_failure", len(runner.steps) == 2 and
           "não teve sucesso/verificação" in model.received[1] and
           "sem sucesso" in final.response.speech_output,
           actions=len(runner.steps))

    # Scenario 4: three failing reads are enough to stop a runaway tool loop.
    runner, registry, _, _ = prepare(root / "case-stall",
        [answer("read_file", {"path": f"/missing/{i}"}) for i in range(5)])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(False, error="missing"))
    final = runner.start("Leia arquivos")
    record("three_failures_stop", len(runner.steps) == 3 and
           "Três tentativas consecutivas" in final.response.speech_output,
           actions=len(runner.steps))

    # Scenario 5: read-only specialist delegates can use four reads + report.
    registry = ToolRegistry()
    llm = OfflineLLM([answer("read_file", {"path": f"doc-{i}"}) for i in range(4)] +
                     [answer(speech="Relatório de quatro documentos")])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, p["path"]))
    team = AgentTeam(llm, registry, AuditLogger(root / "case-team" / "logs"))
    result = team.run([{"role": "arquivos", "task": "Ler documentos", "max_steps": 5}])
    record("deep_readonly_agent", result.ok and result.meta["agents"][0]["steps"] == 5 and
           "Relatório" in result.output, steps=result.meta["agents"][0]["steps"])

    # Scenario 6: interruption prevents the second tool effect.
    runner, registry, _, _ = prepare(root / "case-cancel", [
        answer("read_file", {"path": str(paths[0])}),
        answer("read_file", {"path": str(paths[1])}),
    ])
    actions = []
    registry.register(ToolSpec("read_file", "read"), lambda p: (
        actions.append(p["path"]) or ToolResult(True, Path(p["path"]).read_text(encoding="utf-8"))
    ))
    def cancel_after_first(event):
        if event.get("phase") == "observed":
            runner.cancel()
    runner.start("Leia dois arquivos", cancel_after_first)
    record("cancel_between_effects", len(actions) == 1 and not runner.active,
           executed=len(actions))

    # Scenario 7: end-to-end approved file write with independent SHA goal.
    target = root / "contract_answer.txt"
    payload = "verifiable\n"
    spec = {"kind": "file_sha256", "path": str(target),
            "sha256": hashlib.sha256(payload.encode()).hexdigest()}
    runner, registry, _, _ = prepare(root / "case-goal", [
        answer("write_file", {"path": str(target), "content": payload}),
        answer(speech="Arquivo pronto"),
    ], acceptance_roots=[root])
    file_tool = FileTool([root])
    registry.register(ToolSpec("write_file", "write", sensitive=True), file_tool.write_file)
    approval = runner.start("Grave a resposta", acceptance=spec)
    finished = runner.resume(approval.pending_action, True) if approval.needs_confirmation else approval
    record("verified_goal_after_approval",
           bool(approval.needs_confirmation) and target.read_text() == payload and
           runner.goal_verdict["status"] == "VERIFIED" and
           "NÃO verificada" not in finished.response.speech_output,
           goal_verdict=runner.goal_verdict["status"])

    # Scenario 8: an already-existing file must NOT masquerade as this task's output.
    runner, registry, _, _ = prepare(root / "case-old", [
        answer(speech="O arquivo foi criado"),
    ], acceptance_roots=[root])
    result = runner.start("Grave a resposta", acceptance=spec)
    record("preexisting_file_is_not_proof",
           runner.goal_verdict["reason"] == "no_verified_write" and
           "NÃO verificada" in result.response.speech_output,
           goal_verdict=runner.goal_verdict["status"])

    # Scenario 9: model cannot gain a destructive tool via a goal contract.
    doomed = root / "doomed.txt"
    doomed.write_text("must be preserved")
    runner, registry, _, _ = prepare(root / "case-delete", [
        answer("delete_file", {"path": str(doomed)}),
    ], acceptance_roots=[root])
    registry.register(ToolSpec("delete_file", "delete", destructive=True),
                      file_tool.delete_file)
    answer_result = runner.start("Exclua o arquivo", acceptance={
        "kind": "file_absent", "path": str(doomed),
    })
    record("goal_contract_never_grants_delete_permission",
           not answer_result.needs_confirmation and not answer_result.executed and
           doomed.read_text() == "must be preserved" and
           runner.goal_verdict["reason"] == "no_verified_delete",
           goal_verdict=runner.goal_verdict["status"])

    # Scenario 10: the code project is not delivered until BOTH files pass.
    source = root / "bundle_app.py"
    tests = root / "bundle_test.py"
    src_text = "def answer():\n    return 42\n"
    test_text = "def test_answer():\n    assert answer() == 42\n"
    manifest = {"kind": "file_bundle", "items": [
        {"kind": "file_sha256", "path": str(source),
         "sha256": hashlib.sha256(src_text.encode()).hexdigest()},
        {"kind": "file_sha256", "path": str(tests),
         "sha256": hashlib.sha256(test_text.encode()).hexdigest()},
    ]}
    runner, registry, _, _ = prepare(root / "case-bundle-complete", [
        answer("write_file", {"path": str(source), "content": src_text}),
        answer("write_file", {"path": str(tests), "content": test_text}),
        answer(speech="Dois arquivos entregues"),
    ], acceptance_roots=[root])
    registry.register(ToolSpec("write_file", "write", sensitive=True), file_tool.write_file)
    first = runner.start("Entregue código e testes", acceptance=manifest)
    second = runner.resume(first.pending_action, True) if first.needs_confirmation else first
    last = runner.resume(second.pending_action, True) if second.needs_confirmation else second
    record("bundle_code_and_test_both_verified",
           first.needs_confirmation and second.needs_confirmation and
           source.read_text() == src_text and tests.read_text() == test_text and
           runner.goal_verdict["reason"] == "all_files_verified" and
           "NÃO verificada" not in last.response.speech_output,
           goal_verdict=runner.goal_verdict["status"])

    # Scenario 11: "done" after writing only code is not a complete project.
    other = root / "partial_app.py"
    absent = root / "partial_test.py"
    partial = {"kind": "file_bundle", "items": [
        {"kind": "file_sha256", "path": str(other),
         "sha256": hashlib.sha256(src_text.encode()).hexdigest()},
        {"kind": "file_sha256", "path": str(absent),
         "sha256": hashlib.sha256(test_text.encode()).hexdigest()},
    ]}
    runner, registry, _, _ = prepare(root / "case-bundle-partial", [
        answer("write_file", {"path": str(other), "content": src_text}),
        answer(speech="Já terminei o projeto"),
    ], acceptance_roots=[root])
    registry.register(ToolSpec("write_file", "write", sensitive=True), file_tool.write_file)
    approval = runner.start("Entregue código e testes", acceptance=partial)
    final = runner.resume(approval.pending_action, True) if approval.needs_confirmation else approval
    record("bundle_incomplete_delivery_is_not_verified",
           approval.needs_confirmation and other.exists() and not absent.exists() and
           runner.goal_verdict["reason"] == "verified_1_of_2" and
           "NÃO verificada" in final.response.speech_output,
           goal_verdict=runner.goal_verdict["status"])

    return checks


def main():
    with tempfile.TemporaryDirectory(prefix="nyx-eval-") as path:
        checks = evaluate(Path(path))
    output = {"type": "scripted_regression", "real_llm_evaluated": False,
              "passed": sum(item["passed"] for item in checks),
              "total": len(checks), "scenarios": checks}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["passed"] == output["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
