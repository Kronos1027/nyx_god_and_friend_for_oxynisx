"""High-depth read-only agents; no Windows services, network or model weights."""
import json

from audit.logger import AuditLogger
from core.agent_team import AgentTeam
from core.task_graph import normalize_tasks
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def answer(tool="none", params=None, text="Resultado verificado"):
    return json.dumps({
        "emotion": "idle", "action": {"type": tool, "params": params or {}},
        "requires_confirmation": False, "speech_output": text,
    })


def setup(tmp_path, model):
    registry = ToolRegistry()
    calls = []
    registry.register(ToolSpec("read_file", "read-only fixture"), lambda p: (
        calls.append(p["path"]) or ToolResult(True, "Conteúdo-" + p["path"])
    ))
    team = AgentTeam(model, registry, AuditLogger(tmp_path, "deep-agent"))
    return team, calls


def test_deep_agent_reads_multiple_sources_and_reports(tmp_path):
    class Model:
        def __init__(self):
            self.calls = []
        def generate(self, prompt, history=None):
            self.calls.append(prompt)
            n = len(self.calls)
            if n < 5:
                return answer("read_file", {"path": str(n)})
            return answer(text="Relatório com Conteúdo-1, Conteúdo-2, Conteúdo-3, Conteúdo-4.")
    model = Model()
    team, calls = setup(tmp_path, model)
    result = team.run([{"role": "arquivos", "task": "Leia quatro partes", "max_steps": 5}])
    assert result.ok and calls == ["1", "2", "3", "4"]
    assert len(model.calls) == 5
    assert result.meta["max_steps"] == 5
    assert result.meta["agents"][0]["steps"] == 5
    assert "nenhuma; entregue o relatório" in model.calls[-1]


def test_deep_agent_final_turn_never_runs_tool(tmp_path):
    class Model:
        def __init__(self):
            self.calls = 0
        def generate(self, prompt, history=None):
            self.calls += 1
            return answer("read_file", {"path": str(self.calls)})
    team, calls = setup(tmp_path, Model())
    result = team.run([{"role": "arquivos", "task": "Leia até o fim", "max_steps": 4}])
    assert not result.ok
    assert calls == ["1", "2", "3"]
    assert result.meta["agents"][0]["state"] == "INCOMPLETE"
    assert "Conteúdo-3" in result.error


def test_default_preserves_two_step_contract(tmp_path):
    class Model:
        def __init__(self):
            self.calls = 0
        def generate(self, prompt, history=None):
            self.calls += 1
            return answer("read_file", {"path": str(self.calls)})
    team, calls = setup(tmp_path, Model())
    result = team.run([{"role": "arquivos", "task": "Consulta simples"}])
    assert not result.ok and calls == ["1"]
    assert result.meta["max_steps"] == 2


def test_repeated_deep_read_stopped_without_reexecuting(tmp_path):
    class Model:
        def generate(self, prompt, history=None):
            return answer("read_file", {"path": "mesmo"})
    team, calls = setup(tmp_path, Model())
    result = team.run([{"role": "arquivos", "task": "Leia", "max_steps": 6}])
    assert not result.ok and calls == ["mesmo"]
    assert result.meta["agents"][0]["state"] == "INCOMPLETE"


def test_unknown_or_oversized_depth_is_rejected():
    import pytest
    roles = {"arquivos": object()}
    for depth in (0, 1, 7, True, "6", None, -1):
        with pytest.raises(ValueError):
            normalize_tasks([{"role": "arquivos", "task": "algo", "max_steps": depth}], roles)
    assert normalize_tasks([{"role": "arquivos", "task": "algo", "max_steps": 6}], roles)[0]["max_steps"] == 6


def test_dependency_failure_does_not_launch_dependent_deep_agent(tmp_path):
    calls = []
    class Model:
        def generate(self, prompt, history=None):
            calls.append(prompt)
            return answer(text="Vou pesquisar em breve.")
    team, _ = setup(tmp_path, Model())
    result = team.run([
        {"id": "one", "role": "arquivos", "task": "Consultar", "max_steps": 6},
        {"id": "two", "role": "arquivos", "task": "Dependência", "depends_on": ["one"], "max_steps": 6},
    ])
    assert not result.ok and len(calls) == 1
    assert result.meta["agents"][1]["state"] == "DEPENDENCY_FAILED"


def test_deep_investigation_does_not_gain_write_capability(tmp_path):
    executed = []
    class Model:
        def generate(self, prompt, history=None):
            return answer("write_file", {"path": "x", "content": "unsafe"})
    team, _ = setup(tmp_path, Model())
    team.registry.register(ToolSpec("write_file", "write"), lambda p: (
        executed.append(p) or ToolResult(True, "x")
    ))
    result = team.run([{"role": "arquivos", "task": "Altere arquivo", "max_steps": 6}])
    assert not result.ok and not executed
    assert "fora do escopo" in result.error
