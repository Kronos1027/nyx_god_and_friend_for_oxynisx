import json

import pytest

from core.evolution import EvolutionLab, evolution_contract, make_evolution_tool_func
from tools.registry import ToolRegistry, ToolSpec, ToolResult


def test_planning_notes_are_relevant_bounded_and_unverified(tmp_path):
    import json
    lab = EvolutionLab(tmp_path / "lab.db")
    lab.learn("Python arquivos", "Conteúdo externo " * 250, "https://docs.python.org/3/")
    lab.learn("Receita", "Bolo de chocolate", "https://example.org/bolo")
    context = lab.planning_context("Quero criar arquivos Python")
    rows = json.loads(context.split("\n", 1)[1])
    assert len(rows) == 1
    assert rows[0]["source"] == "https://docs.python.org/3/"
    assert rows[0]["verified"] is False
    assert len(rows[0]["excerpt"]) <= 450
    assert lab.planning_context("astronomia") == ""


def test_learn_persists_provenance_and_deduplicates(tmp_path):
    lab = EvolutionLab(tmp_path / "lab.db")
    item = lab.learn("Python", "Uma nota de estudo", "https://docs.python.org/3/")
    assert item["verified"] is False
    assert lab.learn("Python", "Uma nota de estudo", "https://docs.python.org/3/")["duplicate"]
    assert EvolutionLab(lab.path).search("Python")[0]["source"] == "https://docs.python.org/3/"
    assert lab.search("%") == []


@pytest.mark.parametrize("url", ["file:///secret", "https://user:pass@example.org", "javascript:alert(1)", ""])
def test_invalid_sources_rejected(tmp_path, url):
    with pytest.raises(ValueError):
        EvolutionLab(tmp_path / "lab.db").learn("A", "B", url)


def test_simulation_never_executes_tools_or_promotes_code(tmp_path):
    lab = EvolutionLab(tmp_path / "lab.db")
    registry = ToolRegistry()
    calls = []
    registry.register(ToolSpec("write_file", "test", sensitive=True), lambda p: calls.append(p))
    item = lab.propose("Example", [{"tool": "write_file", "params": {"path": "x"}, "expected": "file created"}])
    result = lab.simulate(item["id"], registry)
    assert result["structurally_valid"]
    assert not result["behavior_verified"]
    assert result["checks"][0]["requires_review"]
    assert calls == []
    assert lab.overview()["proposals"][0]["status"] == "simulated"
    assert make_evolution_tool_func(lab, registry)({"operation": "status"}).ok


def test_unknown_tool_and_limits(tmp_path):
    lab = EvolutionLab(tmp_path / "lab.db")
    item = lab.propose("Unknown", [{"tool": "invented", "params": {}, "expected": "nothing"}])
    assert not lab.simulate(item["id"], ToolRegistry())["structurally_valid"]
    with pytest.raises(ValueError):
        lab.propose("Code", [{"code": "print('hi')"}])
    lab.MAX_ITEMS = 0
    with pytest.raises(ValueError):
        lab.learn("A", "B", "https://example.org")


def test_tool_registry_barrier_reports_invalid_input(tmp_path):
    lab = EvolutionLab(tmp_path / "lab.db")
    registry = ToolRegistry()
    registry.register(ToolSpec("evolution", "lab"), make_evolution_tool_func(lab, registry))
    result = registry.execute("evolution", {"operation": "learn"})
    assert isinstance(result, ToolResult) and not result.ok


def test_query_without_operation_searches_notes_instead_of_returning_status(tmp_path):
    lab = EvolutionLab(tmp_path / "lab.db")
    lab.learn("Python", "Uma nota sobre geradores", "https://docs.python.org/3/")
    tool = make_evolution_tool_func(lab, ToolRegistry())
    result = tool({"query": "geradores"})
    assert result.ok and result.meta["operation"] == "search"
    assert [item["topic"] for item in json.loads(result.output)] == ["Python"]
    assert "knowledge_count" not in result.output
    assert json.loads(tool({"operation": "status"}).output)["knowledge_count"] == 1


@pytest.mark.parametrize("params", [{}, {"topic": "Python"}, {"query": "Python", "content": "incompleto"},
                                   {"operation": None}, {"operation": []}])
def test_ambiguous_missing_operation_is_not_silently_successful(tmp_path, params):
    lab = EvolutionLab(tmp_path / "lab.db")
    registry = ToolRegistry()
    registry.register(ToolSpec("evolution", "lab"), make_evolution_tool_func(lab, registry))
    result = registry.execute("evolution", params)
    assert not result.ok and "Informe operation" in result.error
    assert lab.overview()["knowledge_count"] == 0


def test_simulation_respects_dynamic_review_and_runtime_disabled_tools(tmp_path):
    lab = EvolutionLab(tmp_path / "lab.db")
    registry = ToolRegistry()
    registry.register(ToolSpec("browser", "browser", sensitive_probe=lambda p: p["action"] == "click"),
                      lambda p: pytest.fail("Simulation must not execute tools"))
    proposal = lab.propose("Dynamic policy", [
        {"tool": "browser", "params": {"action": "read"}, "expected": "read page"},
        {"tool": "browser", "params": {"action": "click"}, "expected": "click reviewed"}])
    report = lab.simulate(proposal["id"], registry)
    assert report["structurally_valid"] and not report["executed"]
    assert [check["requires_review"] for check in report["checks"]] == [False, True]
    registry.disabled_tools.add("browser")
    report = lab.simulate(proposal["id"], registry)
    assert not report["structurally_valid"] and not report["executed"]
    assert all(check["registered"] and not check["available"] and check["requires_review"]
               for check in report["checks"])


def test_evolution_contract_covers_the_real_queue_operations():
    contract = evolution_contract()
    assert {"study", "studies", "cancel_study"} <= set(contract["operation"].split("|"))
    assert contract["required"]["study"] == ["topic", "url"]
