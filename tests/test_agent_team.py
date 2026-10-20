import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from audit.logger import AuditLogger
from core.agent_team import AgentTeam
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def response(action=None, speech="feito"):
    return json.dumps({
        "reasoning": "",
        "alternative_suggestion": None,
        "emotion": "talk",
        "action": action or {"type": "none", "params": {}},
        "requires_confirmation": False,
        "confirmation_prompt": None,
        "speech_output": speech,
    })


def test_agent_team_runs_two_independent_agents_concurrently(tmp_path):
    class ParallelLLM:
        def generate(self, user_input, history=None):
            return response({"type": "read_file", "params": {"path": "notes.txt"}})

    barrier = threading.Barrier(2)
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="read_file", description="read"),
        lambda params: (barrier.wait(timeout=2), ToolResult(ok=True, output="análise concluída"))[1],
    )

    audit = AuditLogger(tmp_path, "team")
    result = AgentTeam(ParallelLLM(), registry, audit).run([
        {"role": "pesquisa", "task": "pesquisa A"},
        {"role": "pesquisa", "task": "pesquisa B"},
    ])
    assert result.ok is True
    assert result.meta["max_parallel"] == 2
    assert len(result.meta["agents"]) == 2
    assert result.output.count("[pesquisa]") == 2


def test_agent_team_denies_tool_outside_role_scope(tmp_path):
    class UnsafeLLM:
        def generate(self, user_input, history=None):
            return response({"type": "shell", "params": {"template": "list_dir"}})

    registry = ToolRegistry()
    registry.register(ToolSpec(name="shell", description="shell"), lambda params: ToolResult(ok=True, output="ran"))
    audit = AuditLogger(tmp_path, "team-deny")
    result = AgentTeam(UnsafeLLM(), registry, audit).run([
        {"role": "pesquisa", "task": "faça isso"},
    ])
    assert result.ok is False
    assert "fora do escopo" in result.output
    security = [event for event in audit.read_all() if event.get("event") == "security"]
    assert security[-1]["code"] == "micro_agent_tool_denied"


def test_agent_team_rejects_oversized_or_invalid_requests(tmp_path):
    audit = AuditLogger(tmp_path, "team-input")
    team = AgentTeam(object(), ToolRegistry(), audit)
    too_many = team.run([{"role": "pesquisa", "task": "A"}] * 3)
    invalid = team.run([{"role": "pesquisa", "task": "x" * 501}])
    unknown_role = team.run([{"role": "admin", "task": "A"}])
    assert too_many.ok is False and too_many.meta["max_agents"] == 2
    assert invalid.ok is False
    assert unknown_role.ok is False


def test_agent_team_executes_only_scoped_registered_read_tool(tmp_path):
    class ReadLLM:
        def generate(self, user_input, history=None):
            return response({"type": "read_file", "params": {"path": "notes.txt"}})

    registry = ToolRegistry()
    registry.register(ToolSpec(name="read_file", description="read"),
                      lambda params: ToolResult(ok=True, output="conteúdo") if params["path"] == "notes.txt" else ToolResult(ok=False))
    result = AgentTeam(ReadLLM(), registry, AuditLogger(tmp_path, "team-read")).run([
        {"role": "arquivos", "task": "leia notes.txt"},
    ])
    assert result.ok is True
    assert "conteúdo" in result.output


def test_agent_team_blocks_sensitive_web_and_git_subactions(tmp_path):
    class SensitiveLLM:
        def __init__(self, action):
            self.action = action

        def generate(self, user_input, history=None):
            return response(self.action)

    registry = ToolRegistry()
    registry.register(ToolSpec(name="web", description="web"), lambda params: ToolResult(ok=True, output="executou"))
    registry.register(ToolSpec(name="project_status", description="status"), lambda params: ToolResult(ok=True, output="executou"))
    audit = AuditLogger(tmp_path, "team-sensitive")

    location = AgentTeam(SensitiveLLM({"type": "web", "params": {"action": "location"}}), registry, audit).run([
        {"role": "pesquisa", "task": "busque"},
    ])
    weather = AgentTeam(SensitiveLLM({"type": "web", "params": {"action": "search", "query": "previsão do tempo em casa"}}), registry, audit).run([
        {"role": "pesquisa", "task": "busque"},
    ])
    git_path = AgentTeam(SensitiveLLM({"type": "project_status", "params": {"action": "git", "path": "C:/"}}), registry, audit).run([
        {"role": "sistema", "task": "verifique"},
    ])
    assert location.ok is False and "fora do escopo" in location.output
    assert weather.ok is False and "fora do escopo" in weather.output
    assert git_path.ok is False and "fora do escopo" in git_path.output

