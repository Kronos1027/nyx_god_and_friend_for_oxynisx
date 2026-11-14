"""Reproducible agent reliability smoke suite (scripted model, real agent runner).

Does NOT measure a local LLM's ability, GPU latency or Windows UI acceptance.
Runs only temporary file operations and read-only delegates. No external URLs.
Usage: python tools/evaluate_agent_reliability.py
"""
from __future__ import annotations

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


def answer(tool="none", params=None, speech="Conclusão"):
    return json.dumps({"emotion": "idle", "speech_output": speech,
                       "action": {"type": tool, "params": params or {}},
                       "requires_confirmation": False}, ensure_ascii=False)


def prepare(root, replies):
    registry = ToolRegistry()
    llm = OfflineLLM(replies)
    loop = AgentLoop(llm, registry, AuditLogger(root / "logs"))
    return TaskRunner(loop), registry, llm, loop


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
