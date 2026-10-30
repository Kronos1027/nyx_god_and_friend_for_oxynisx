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
            if "análise concluída" in user_input:
                return response(speech="A consulta retornou análise concluída.")
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
    too_many = team.run([{"role": "pesquisa", "task": "A"}] * 5)
    invalid = team.run([{"role": "pesquisa", "task": "x" * 501}])
    unknown_role = team.run([{"role": "admin", "task": "A"}])
    assert too_many.ok is False and too_many.meta["max_agents"] == 4
    assert invalid.ok is False
    assert unknown_role.ok is False


def test_agent_team_executes_only_scoped_registered_read_tool(tmp_path):
    class ReadLLM:
        def generate(self, user_input, history=None):
            if "conteúdo" in user_input:
                return response(speech="O arquivo contém: conteúdo.")
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



def test_agent_team_accepts_four_roles_and_reports_parallelism(tmp_path):
    class QuietLLM:
        def generate(self, user_input, history=None):
            return response(speech="nada a consultar")

    registry = ToolRegistry()
    for name in ("web", "read_file", "find_files", "project_status", "browser"):
        registry.register(ToolSpec(name=name, description=name),
                          lambda params: ToolResult(ok=True, output="ok"))

    result = AgentTeam(QuietLLM(), registry, AuditLogger(tmp_path, "team4")).run([
        {"role": "pesquisa", "task": "a"},
        {"role": "arquivos", "task": "b"},
        {"role": "sistema", "task": "c"},
        {"role": "codigo", "task": "d"},
    ])

    assert result.ok is True
    assert len(result.meta["agents"]) == 4
    assert result.meta["max_parallel"] == 3
    assert result.meta["max_steps"] == 2
    assert result.output.count("[") == 4


def test_agent_team_uses_two_steps_and_summarizes_the_answer(tmp_path):
    class TwoStepLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, user_input, history=None):
            self.calls += 1
            if self.calls == 1:
                return response({"type": "read_file", "params": {"path": "notes.txt"}})
            assert "conteúdo" in user_input
            return response(speech="O arquivo diz: conteúdo")

    registry = ToolRegistry()
    registry.register(ToolSpec(name="read_file", description="read"),
                      lambda params: ToolResult(ok=True, output="conteúdo"))
    llm = TwoStepLLM()

    result = AgentTeam(llm, registry, AuditLogger(tmp_path, "team-step")).run([
        {"role": "arquivos", "task": "leia notes.txt"},
    ])

    assert result.ok is True
    assert "conteúdo" in result.output
    assert result.meta["agents"][0]["steps"] == 2
    assert llm.calls == 2


def test_agent_team_stops_when_a_tool_would_repeat(tmp_path):
    class RepeatingLLM:
        def generate(self, user_input, history=None):
            return response({"type": "read_file", "params": {"path": "notes.txt"}})

    calls = []
    registry = ToolRegistry()
    registry.register(ToolSpec(name="read_file", description="read"),
                      lambda params: (calls.append(params), ToolResult(ok=True, output="conteúdo"))[1])

    result = AgentTeam(RepeatingLLM(), registry, AuditLogger(tmp_path, "team-loop")).run([
        {"role": "arquivos", "task": "leia"},
    ])

    assert result.ok is False
    assert len(calls) == 1
    assert "conteúdo" in result.output
    assert result.meta["agents"][0]["state"] == "INCOMPLETE"


def test_browser_agent_cannot_click_or_open_local_files(tmp_path):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="browser", description="browser",
                 sensitive_probe=lambda params: params.get("action") == "click"),
        lambda params: ToolResult(ok=True, output="executou"),
    )
    audit = AuditLogger(tmp_path, "team-browser")

    class ClickLLM:
        def generate(self, user_input, history=None):
            return response({"type": "browser", "params": {"action": "click", "selector": "#buy"}})

    class FileLLM:
        def generate(self, user_input, history=None):
            return response({"type": "browser", "params": {"action": "open", "url": "file:///C:/Windows/win.ini"}})

    click = AgentTeam(ClickLLM(), registry, audit).run([{"role": "navegador", "task": "clique"}])
    local = AgentTeam(FileLLM(), registry, audit).run([{"role": "navegador", "task": "abra"}])

    assert click.ok is False
    assert local.ok is False
    details = [str(event.get("detail", "")) for event in audit.read_all() if event.get("event") == "security"]
    assert any("http(s)" in detail for detail in details)


def test_patch_role_blocks_test_execution_even_without_apply(tmp_path):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="code_task",
            description="code_task",
            destructive=False,
            sensitive=False,
            destructive_probe=lambda p: bool(p.get("apply")),
            sensitive_probe=lambda p: bool(p.get("apply")),
        ),
        lambda params: ToolResult(ok=True, output="Plano proposto: modifique test.py", meta={"applied": False}),
    )
    audit = AuditLogger(tmp_path, "team-patch-ok")

    class PatchLLM:
        def generate(self, user_input, history=None):
            return response({"type": "code_task", "params": {"task": "conserte", "path": "repo"}})

    result = AgentTeam(PatchLLM(), registry, audit).run([{"role": "patch", "task": "investigue e proponha"}])
    assert result.ok is False
    assert any("executar testes também executa código" in str(e) for e in audit.read_all())


def test_patch_role_blocks_direct_code_task_apply(tmp_path):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="code_task",
            description="code_task",
            destructive=False,
            sensitive=False,
            destructive_probe=lambda p: bool(p.get("apply")),
            sensitive_probe=lambda p: bool(p.get("apply")),
        ),
        lambda params: ToolResult(ok=True, output="aplicado"),
    )
    audit = AuditLogger(tmp_path, "team-patch-deny")

    class ApplyLLM:
        def generate(self, user_input, history=None):
            return response({"type": "code_task", "params": {"task": "conserte", "apply": True}})

    result = AgentTeam(ApplyLLM(), registry, audit).run([{"role": "patch", "task": "aplique a correção"}])
    assert result.ok is False
    assert "fora do escopo" in result.output or "não tem permissão" in result.output
    security = [event for event in audit.read_all() if event.get("event") == "security"]
    assert any("microagente não tem permissão para aplicar" in str(s.get("detail", "")) for s in security)


def test_browser_agent_allows_structured_read_actions(tmp_path):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="browser", description="browser"),
        lambda params: ToolResult(ok=True, output=f"ação {params.get('action')} executada"),
    )
    audit = AuditLogger(tmp_path, "team-browser-struct")

    class StructBrowserLLM:
        def generate(self, user_input, history=None):
            if "ação links executada" in user_input:
                return response(speech="Observação: ação links executada.")
            return response({"type": "browser", "params": {"action": "links"}})

    result = AgentTeam(StructBrowserLLM(), registry, audit).run([{"role": "navegador", "task": "extraia links"}])
    assert result.ok is True
    assert "ação links executada" in result.output


def test_role_catalog_restricts_registered_actions_and_final_turn(tmp_path):
    catalogs = []
    class Model:
        def generate(self, prompt, history=None, task_tools=None):
            catalogs.append(task_tools)
            return response({"type": "browser", "params": {"action": "links"}}) if len(catalogs) == 1 else response(speech="Página retornou três links.")
    registry = ToolRegistry()
    contract = {"action": "read|links|click|type|close", "url": "https"}
    registry.register(ToolSpec("browser", "browser", input_contract=contract,
                              sensitive_probe=lambda p: p.get("action") == "read"),
                      lambda p: ToolResult(True, "três links"))
    result = AgentTeam(Model(), registry, AuditLogger(tmp_path)).run([{"role": "navegador", "task": "Liste links"}])
    assert result.ok
    assert catalogs[0][0]["params_contract"]["action"] == "links"
    assert catalogs[1] == []
    assert contract["action"] == "read|links|click|type|close"


def test_child_catalog_excludes_disabled_sensitive_destructive_and_foreign_tools(tmp_path):
    captured = []
    class Model:
        def generate(self, prompt, **kwargs):
            captured.append(kwargs["task_tools"])
            return response(speech="Não há consultas disponíveis para esta investigação.")
    registry = ToolRegistry()
    registry.register(ToolSpec("read_file", "read", sensitive=True), lambda p: None)
    registry.register(ToolSpec("find_files", "find", destructive=True), lambda p: None)
    registry.register(ToolSpec("web", "web"), lambda p: None)
    registry.register(ToolSpec("skills", "skills"), lambda p: None)
    registry.disabled_tools.add("web")
    result = AgentTeam(Model(), registry, AuditLogger(tmp_path)).run([{"role": "pesquisa", "task": "Investigue"}])
    assert result.ok and captured == [[]]
    assert result.meta["agents"][0]["evidence_kind"] == "analysis_only"


def test_scoped_catalog_reaches_real_client_schema_without_running_model(tmp_path, monkeypatch):
    from core.llm_client import OllamaClient
    payloads = []
    def post(url, payload, timeout):
        payloads.append(payload)
        return {"message": {"content": response(speech="A investigação requer um caminho de arquivo.")}}
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", post)
    registry = ToolRegistry()
    registry.register(ToolSpec("read_file", "read"), lambda p: None)
    registry.register(ToolSpec("skills", "skills"), lambda p: None)
    result = AgentTeam(OllamaClient(), registry, AuditLogger(tmp_path)).run([{"role": "pesquisa", "task": "Investigue arquivos"}])
    assert result.ok
    assert payloads[0]["format"]["properties"]["action"]["properties"]["type"]["enum"] == ["none", "read_file"]
    assert "operation=\"learn\"" not in payloads[0]["messages"][0]["content"]


def test_skill_scope_failure_reports_actionable_reason(tmp_path):
    class Model:
        def generate(self, prompt, **kwargs):
            return response({"type": "skills", "params": {"op": "list"}})
    result = AgentTeam(Model(), ToolRegistry(), AuditLogger(tmp_path)).run([{"role": "pesquisa", "task": "Liste o catálogo"}])
    assert not result.ok and "skills" in result.error and "ferramenta direta" in result.error
    assert result.meta["agents"][0]["state"] == "SCOPE_DENIED"


def test_future_only_report_is_incomplete_and_blocks_dependency(tmp_path):
    calls = []
    class Model:
        def generate(self, prompt, **kwargs):
            calls.append(prompt)
            return response(speech="Vou verificar o catálogo de habilidades locais para Python e Ollama. Por favor, aguarde um momento.")
    result = AgentTeam(Model(), ToolRegistry(), AuditLogger(tmp_path)).run([
        {"id": "research", "role": "pesquisa", "task": "Liste o catálogo"},
        {"id": "dependent", "role": "codigo", "task": "Analise o catálogo", "depends_on": ["research"]}])
    assert not result.ok and len(calls) == 1
    assert [a["state"] for a in result.meta["agents"]] == ["INCOMPLETE", "DEPENDENCY_FAILED"]


def test_final_turn_cannot_execute_a_second_unsummarized_consultation(tmp_path):
    generated, executed = [], []
    class Model:
        def generate(self, prompt, **kwargs):
            generated.append(prompt)
            return response({"type": "read_file", "params": {"path": str(len(generated))}})
    registry = ToolRegistry()
    registry.register(ToolSpec("read_file", "read"), lambda p: executed.append(p) or ToolResult(True, "conteúdo parcial"))
    result = AgentTeam(Model(), registry, AuditLogger(tmp_path)).run([{"role": "arquivos", "task": "Leia arquivos"}])
    assert not result.ok and len(executed) == 1
    assert result.meta["agents"][0]["state"] == "INCOMPLETE"
    assert result.meta["agents"][0]["partial_output"] == "conteúdo parcial"


def test_internal_model_typeerror_is_not_retried_with_legacy_signature(tmp_path):
    calls = []
    class Model:
        def generate(self, prompt, **kwargs):
            calls.append(kwargs)
            raise TypeError("internal failure")
    result = AgentTeam(Model(), ToolRegistry(), AuditLogger(tmp_path)).run([{"role": "pesquisa", "task": "Analise"}])
    assert not result.ok and len(calls) == 1
    assert "internal failure" in result.error
