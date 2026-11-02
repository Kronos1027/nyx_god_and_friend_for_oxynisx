import copy
import json
from pathlib import Path

import pytest

from audit.logger import AuditLogger
from config import PermissionMode
from core.agent_loop import AgentLoop
from core.llm_client import OfflineLLM
from core.task_runner import TaskRunner
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def reply(tool="none", params=None, speech="Pronto"):
    return json.dumps({"reasoning": "test", "alternative_suggestion": None, "emotion": "talk",
                       "action": {"type": tool, "params": params or {}}, "requires_confirmation": False,
                       "confirmation_prompt": None, "speech_output": speech})


def make_runner(tmp_path, responses, **kwargs):
    registry = ToolRegistry()
    loop = AgentLoop(OfflineLLM(responses), registry, AuditLogger(tmp_path / "logs", session_id="task-test"))
    runner = TaskRunner(loop, **kwargs)
    return runner, loop, registry


@pytest.mark.parametrize('final_verified', [False, True])
def test_native_app_focus_is_rechecked_after_final_model_response(tmp_path, monkeypatch, final_verified):
    runner, loop, registry = make_runner(tmp_path, [reply('ui_action', {'action':'open_app','app':'Fixture'}),
                                                  reply(speech='Janela aberta e em foco.')])
    target = {'executable':'C:/Fixture/app.exe', 'app_id':None}
    registry.register(ToolSpec('ui_action','ui'), lambda params:ToolResult(True, 'foco observado',
        meta={**target, 'verified':True, 'windows':[{'hwnd':42}], 'launch_kind':'native', 'check':'installed_app_window'}))
    checks = []
    def recheck(observed):
        checks.append(observed)
        return {'verified':final_verified, 'error_code':None if final_verified else 'UNVERIFIED',
                'details':'Foco mudou durante a resposta.'}
    monkeypatch.setattr('tools.installed_apps.native_app_postcondition', recheck)
    result = runner.start('Abra Fixture.')
    assert checks == [target] and len(runner.steps) == 1
    assert runner.steps[-1]['verified'] == final_verified
    if final_verified:
        assert result.response.speech_output == 'Janela aberta e em foco.'
    else:
        assert 'não posso confirmar' in result.response.speech_output
        assert 'Foco mudou durante a resposta.' in result.response.speech_output
    event = next(row for row in reversed(loop.audit.read_all()) if row['event']=='task_finished')
    assert event['state'] == ('finished' if final_verified else 'stopped')


def test_native_app_final_read_error_is_honest_and_never_reopens(tmp_path, monkeypatch):
    runner, _, registry = make_runner(tmp_path, [reply('ui_action', {'action':'open_app','app':'Fixture'}), reply()])
    calls = []
    def open_app(params):
        calls.append(params)
        return ToolResult(True, 'janela observada', meta={'executable':'C:/Fixture/app.exe', 'app_id':None,
            'verified':True, 'windows':[{'hwnd':42}], 'launch_kind':'native', 'check':'installed_app_window'})
    registry.register(ToolSpec('ui_action','ui'), open_app)
    def unavailable(target):
        raise OSError('fixture read denied')
    monkeypatch.setattr('tools.installed_apps.native_app_postcondition', unavailable)
    result = runner.start('Abra Fixture.')
    assert len(calls) == 1 and not runner.steps[-1]['verified']
    assert 'fixture read denied' in result.response.speech_output
    assert 'não posso confirmar' in result.response.speech_output


def test_new_task_cannot_clear_emergency_latch(tmp_path):
    from core.operation_control import OperationCancelled
    runner, _, registry = make_runner(tmp_path, [reply()])
    registry.control.stop(emergency=True)
    with pytest.raises(OperationCancelled):
        runner.start("Novo pedido")
    assert not runner.active
    registry.control.resume()
    runner.start("Novo pedido explícito")
    assert not runner.active


@pytest.mark.parametrize('app,wrong_tool,wrong_params', [('Edge','browser',{'action':'open','url':'https://example.test'}),
                                                       ('Terminal','shell',{'template':'GET_PROCESS'}),
                                                       ('Discord','browser',{'action':'open','url':'https://discord.com'})])
def test_named_app_is_not_replaced_by_unrequested_navigation_or_command(tmp_path, app, wrong_tool, wrong_params):
    runner, _, registry = make_runner(tmp_path, [reply(wrong_tool, wrong_params),
        reply('ui_action', {'action':'open_app','app':app}), reply(speech='Aplicativo aberto.')])
    registry.register(ToolSpec('browser','browser'), lambda params:pytest.fail('Unrequested site navigation'))
    registry.register(ToolSpec('shell','shell'), lambda params:pytest.fail('Process listing does not open Terminal'))
    calls = []
    registry.register(ToolSpec('ui_action','ui'), lambda params:calls.append(params) or ToolResult(True, 'observed',
        meta={'verified':True,'windows':[{'hwnd':42}],'check':'installed_app_window'}))
    result = runner.start(f'Abre o {app}.')
    assert result.response.speech_output == 'Aplicativo aberto.' and runner.replans == 1
    assert calls == [{'action':'open_app','app':app}]


@pytest.mark.parametrize('goal', ['Abra o Edge em https://example.test', 'Abra o Edge e pesquise astronomia',
                                'Abra a página do Edge', 'Pesquise Chrome'])
def test_browser_grounding_preserves_navigation_and_multi_step_requests(goal):
    from core.app_grounding import explicit_app_issue
    assert explicit_app_issue(goal, 'browser', {'action':'open'}) is None


def test_explicit_no_delegation_filters_catalog_and_blocks_rogue_proposal(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [])
    calls, catalogs = [], []
    registry.register(ToolSpec('agent_team', 'team'), lambda p: (calls.append(p) or ToolResult(True)))
    def generate(prompt, history=None, task_tools=None, **kwargs):
        catalogs.append(task_tools)
        return reply('agent_team', {'tasks': []})
    loop.llm.generate = generate
    result = runner.start('Leia diretamente; não delegue.')
    assert all(t['name'] != 'agent_team' for t in catalogs[0])
    assert calls == []
    assert 'delegação foi excluída' in result.response.speech_output


def test_sum_replans_before_double_counting_and_rejects_wrong_final_total(tmp_path):
    from tools.calculator_tool import calculate
    runner, _, registry = make_runner(tmp_path, [reply('read_file', {'path': 'a.txt'}),
        reply('read_file', {'path': 'b.txt'}), reply('calculator', {'operation': 'sum', 'values': [11, 22]}),
        reply('calculator', {'operation': 'sum', 'values': [33, 22]}), reply(speech='A soma total é 55.'),
        reply(speech='A soma total é 33.')])
    registry.register(ToolSpec('read_file', 'read'), lambda p: ToolResult(True, '11' if p['path'] == 'a.txt' else '22'))
    calls = []
    def calculator(params):
        calls.append(params)
        return calculate(params)
    registry.register(ToolSpec('calculator', 'math'), calculator)
    result = runner.start('Leia os arquivos e calcule a soma.')
    assert result.response.speech_output == 'A soma total é 33.'
    assert len(calls) == 1
    assert runner.replans == 2


def test_file_sum_rejects_an_extra_file_before_execution_and_delivers_answer(tmp_path):
    from tools.calculator_tool import calculate
    runner, _, registry = make_runner(tmp_path, [reply('read_file', {'path': 'a-1.txt'}),
        reply('read_file', {'path': 'a-2.txt'}), reply('calculator', {'values': [11, 22]}),
        reply('read_file', {'path': 'a-3.txt'}), reply(speech='Valores 11 e 22; soma total é 33.')])
    calls = []
    def read(params):
        calls.append(params['path'])
        return ToolResult(True, '11' if params['path'] == 'a-1.txt' else '22')
    registry.register(ToolSpec('read_file', 'read'), read)
    registry.register(ToolSpec('calculator', 'math'), calculate)
    result = runner.start('Leia arquivos a-1.txt até a-2.txt e entregue a soma.')
    assert '33' in result.response.speech_output
    assert calls == ['a-1.txt', 'a-2.txt']
    assert runner.replans == 1


def test_greeting_stream_is_wrapped_as_no_action_without_planner_or_tools(tmp_path):
    from core.conversation import conversation_response
    runner, loop, registry = make_runner(tmp_path, [])
    loop.llm.supports_conversation = True
    registry.register(ToolSpec('shell', 'shell'), lambda p: pytest.fail('Conversa não executa ferramentas.'))
    loop.llm.generate = lambda *args, **kwargs: pytest.fail('Cumprimento não passa pelo planejador JSON.')
    def converse(prompt, history=None, memory_context=None, on_delta=None):
        on_delta('Bom dia!')
        return conversation_response('Bom dia!')
    loop.llm.converse = converse
    events = []
    result = runner.start('Bom dia, Nyx!', events.append)
    assert not result.executed and not runner.steps and not result.needs_confirmation
    assert result.response.action.type == 'none' and result.response.speech_output == 'Bom dia!'
    assert any(event['phase'] == 'conversation_delta' for event in events)


def test_correct_sum_still_replans_when_explicit_calculator_step_was_skipped(tmp_path):
    from tools.calculator_tool import calculate
    runner, _, registry = make_runner(tmp_path, [reply('read_file', {'path':'a.txt'}),
        reply('read_file', {'path':'b.txt'}), reply(speech='Soma total:33.'),
        reply('calculator', {'operation':'sum','values':[11,22]}), reply(speech='Soma total:33.')])
    registry.register(ToolSpec('read_file','read'), lambda p:ToolResult(True, '11' if p['path']=='a.txt' else '22'))
    registry.register(ToolSpec('calculator','math'), calculate)
    result = runner.start('Leia os arquivos e entregue a soma; use calculator.')
    assert result.response.speech_output == 'Soma total:33.'
    assert [step['tool'] for step in runner.steps] == ['read_file','read_file','calculator']
    assert runner.replans == 1


def test_uncertain_external_effect_stops_without_replanning_or_replay(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("ui_action", {"action": "click_element"}),
                                               reply("ui_action", {"action": "click_element"})])
    calls = []
    def uncertain(params):
        calls.append(params)
        return ToolResult(False, error="Timeout após envio", meta={"outcome_unknown": True})
    registry.register(ToolSpec("ui_action", "native UI"), uncertain)
    result = runner.start("Clique uma vez")
    assert len(calls) == 1 and not runner.active
    assert "Confira o estado" in result.response.speech_output


def test_task_catalog_reaches_model_and_internal_typeerror_is_not_retried(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [])
    registry.register(ToolSpec("read_file", "Read a file"), lambda p: ToolResult(True, "ok"))
    calls = []
    class Broken:
        def generate(self, prompt, history=None, memory_context=None, task_tools=None):
            calls.append(task_tools)
            raise TypeError("internal model error")
    loop.llm = Broken()
    result = runner.start("Leia")
    assert calls == [[{"name": "read_file", "description": "Read a file"}]]
    assert "internal model error" in result.response.speech_output
    assert not runner.active


def test_planner_receives_real_shell_parameters_and_omits_disabled_tools(tmp_path):
    from tools.shell_tool import ShellTool
    runner, loop, registry = make_runner(tmp_path, [])
    registry.register(ToolSpec("shell", "commands", input_contract=ShellTool().planner_contract()),
                      lambda p: ToolResult(True))
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True))
    loop.disabled_tools.add("read_file")
    captured = []
    def generate(prompt, **kwargs):
        captured.extend(kwargs["task_tools"])
        return reply()
    loop.llm.generate = generate
    runner.start("Liste arquivos")
    assert [item["name"] for item in captured] == ["shell"]
    listing = next(t for t in captured[0]["params_contract"] if t["template"] == "LIST_DIR")
    assert listing["required"] == {"path": "path"}


def test_planner_retains_all_six_steps_including_first_failure(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [])
    histories = []
    def generate(prompt, history=None, **kwargs):
        histories.append(history)
        n = len(histories)
        return reply("read_file", {"path": str(n)}) if n <= 6 else reply()
    loop.llm.generate = generate
    registry.register(ToolSpec("read_file", "read"),
                      lambda p: ToolResult(p["path"] != "1", output="value-" + p["path"], error="first failed"))
    runner.start("Leia seis arquivos")
    ledger = json.loads(histories[-1][-1]["content"].split("\n", 1)[1])
    assert len(ledger) == 6
    assert ledger[0]["ok"] is False and ledger[0]["output"] == "first failed"
    assert ledger[-1]["output"] == "value-6"


def test_planning_ledger_is_bounded_and_marks_truncation(tmp_path):
    runner, loop, _ = make_runner(tmp_path, [])
    loop.history = [{"role": "user", "content": "x" * 10000}] * 20
    runner.steps = [{"tool": "read_file", "params": {"path": "p" * 8000},
                     "ok": True, "verified": True, "output": "a" * 1600,
                     "output_truncated": True} for _ in range(12)]
    history = runner._planning_history()
    assert sum(len(item["content"]) for item in history) < 6500
    ledger = json.loads(history[-1]["content"].split("\n", 1)[1])
    assert len(ledger) == 12
    assert all(item["output_truncated"] and item["params_truncated"] for item in ledger)


def test_two_real_files_then_answer_with_observations(tmp_path):
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    first.write_text("alpha")
    second.write_text("beta")
    runner, loop, registry = make_runner(tmp_path, [reply("read_file", {"path": str(first)}),
                                                  reply("read_file", {"path": str(second)}), reply(speech="alpha e beta")])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, output=Path(p["path"]).read_text()))
    progress = []
    result = runner.start("Leia os dois arquivos", progress.append)
    assert result.response.speech_output == "alpha e beta"
    assert len(runner.steps) == 2 and not runner.active
    assert [s["output"] for s in runner.steps] == ["alpha", "beta"]
    assert [p["phase"] for p in progress].count("observed") == 2
    assert len(loop.history) == 2  # One user request, no fabricated intermediate user turns.


def test_confirmation_resumes_and_second_action_needs_its_own_approval(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [reply("shell", {"n": 1}), reply("shell", {"n": 2}), reply()])
    loop.mode = PermissionMode.AUTONOMA
    calls = []
    registry.register(ToolSpec("shell", "destructive", destructive=True), lambda p: (calls.append(p) or ToolResult(True, "ok")))
    first = runner.start("Duas ações")
    assert first.needs_confirmation and calls == []
    second = runner.resume(first.pending_action, True)
    assert second.needs_confirmation and calls == [{"n": 1}]
    final = runner.resume(second.pending_action, False)
    assert not final.executed and not runner.active
    assert calls == [{"n": 1}]


def test_pending_action_cannot_be_changed_or_replayed(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("write_file", {"path": "original"})])
    calls = []
    registry.register(ToolSpec("write_file", "write", sensitive=True), lambda p: calls.append(p))
    pending = runner.start("Grave arquivo").pending_action
    tampered = copy.deepcopy(pending)
    tampered["params"]["path"] = "different"
    result = runner.resume(tampered, True)
    assert "não corresponde" in result.response.speech_output and calls == []
    with pytest.raises(ValueError):
        runner.resume(pending, True)


def test_repeat_is_blocked_before_second_execution(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"path": "same"})] * 4)
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: (calls.append(p) or ToolResult(True, "result")))
    result = runner.start("Leia")
    assert len(calls) == 1
    assert "repetição" in result.response.speech_output


def test_replans_duplicate_write_before_asking_for_second_confirmation(tmp_path):
    target = tmp_path / "note.txt"
    write = reply("write_file", {"path": str(target), "content": "hello"})
    runner, loop, registry = make_runner(tmp_path, [write, write, reply("read_file", {"path": str(target)}), reply(speech="hello")])
    from tools.file_tool import FileTool
    files = FileTool([tmp_path])
    registry.register(ToolSpec("write_file", "write", sensitive=True), files.write_file)
    registry.register(ToolSpec("read_file", "read"), files.read_file)
    pending = runner.start("Grave e releia")
    assert pending.needs_confirmation
    result = runner.resume(pending.pending_action, True)
    assert not result.needs_confirmation and not runner.active
    assert runner.replans == 1
    assert [step["tool"] for step in runner.steps] == ["write_file", "read_file"]
    assert all(step["verified"] for step in runner.steps)
    assert "NÃO foi executada" in loop.llm.received[2]


def test_read_modify_read_is_allowed_for_verification(tmp_path):
    path = tmp_path / "config.txt"
    path.write_text("before")
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"path": str(path)}),
                                               reply("write_file", {"path": str(path), "content": "after"}),
                                               reply("read_file", {"path": str(path)}), reply()])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, Path(p["path"]).read_text()))

    def write(p):
        Path(p["path"]).write_text(p["content"])
        return ToolResult(True, "written")

    registry.register(ToolSpec("write_file", "write", sensitive=True), write)
    pending = runner.start("Atualize e confira o arquivo")
    assert pending.needs_confirmation
    runner.resume(pending.pending_action, True)
    assert [step["output"] for step in runner.steps] == ["before", "written", "after"]


def test_action_budget_and_deadline_block_effects(tmp_path):
    now = [0]
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"n": 1}), reply("read_file", {"n": 2})], max_actions=1, clock=lambda: now[0])
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: (calls.append(p) or ToolResult(True, "data")))
    assert "Limite" in runner.start("Leia duas vezes").response.speech_output
    assert len(calls) == 1


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
def test_cancel_or_timeout_during_generation_prevents_next_tool(tmp_path, stop):
    now = [0]
    runner, loop, registry = make_runner(tmp_path, [], clock=lambda: now[0])
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: calls.append(p))

    def generate(*args, **kwargs):
        if stop == "cancel":
            runner.cancel()
        else:
            now[0] = 181
        return reply("read_file")

    loop.llm.generate = generate
    assert not runner.start("Leia").executed
    assert calls == [] and not runner.active


def test_cancel_while_waiting_for_confirmation_prevents_approved_effect(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("write_file")])
    calls = []
    registry.register(ToolSpec("write_file", "write", sensitive=True), lambda p: calls.append(p))
    pending = runner.start("Grave").pending_action
    runner.cancel()
    assert not runner.resume(pending, True).executed
    assert calls == []


def test_failed_tools_are_presented_as_failed_in_final_answer(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("read_file"), reply(speech="Fim")])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(False, error="missing"))
    result = runner.start("Leia")
    assert runner.steps[0]["ok"] is False
    assert "sem sucesso" in result.response.speech_output


def test_invalid_json_stops_without_side_effects(tmp_path):
    runner, _, _ = make_runner(tmp_path, ["invalid"])
    result = runner.start("Pedido")
    assert not result.response.parse_ok and not runner.active and runner.steps == []


def test_automatic_budget_continues_past_six_verified_actions(tmp_path):
    replies = [reply("read_file", {"path": str(i)}) for i in range(8)] + [reply(speech="Oito concluídas")]
    runner, loop, registry = make_runner(tmp_path, replies)
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, "value-" + p["path"]))
    runner.set_budget_profile("default")
    progress = []
    result = runner.start("Leia os oito arquivos", progress.append)
    assert len(runner.steps) == 8 and runner.max_actions == 12
    assert result.response.speech_output == "Oito concluídas"
    assert len([p for p in progress if p["phase"] == "budget_extended"]) == 1
    assert any(e["event"] == "task_budget_extended" for e in loop.audit.read_all())


def test_automatic_budget_does_not_extend_failed_work(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"path": str(i)}) for i in range(8)])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(p["path"] != "0", output="value", error="missing"))
    runner.set_budget_profile("default")
    result = runner.start("Leia os arquivos")
    assert len(runner.steps) == 6 and runner.max_actions == 6
    assert "Sem progresso" in result.response.speech_output


def test_null_ui_fields_do_not_evade_repeat_detection():
    assert TaskRunner._signature("ui_action", {"action": "list_windows"}) == TaskRunner._signature(
        "ui_action", {"action": "list_windows", "hwnd": None, "snapshot": None})


def test_automatic_budget_keeps_global_ceiling(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"path": str(i)}) for i in range(49)])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, "value"))
    runner.set_budget_profile("default")
    result = runner.start("Leia os arquivos")
    assert len(runner.steps) == runner.AUTO_ACTION_CEILING == 48
    assert "Limite geral" in result.response.speech_output


def test_automatic_budget_preserves_cancellation_after_extension(tmp_path):
    runner, _, registry = make_runner(tmp_path, [reply("read_file", {"path": str(i)}) for i in range(10)])
    registry.register(ToolSpec("read_file", "read"), lambda p: ToolResult(True, "value"))
    runner.set_budget_profile("default")
    def progress(event):
        if event["phase"] == "observed" and event["step"] == 7:
            runner.cancel()
    result = runner.start("Leia os arquivos", progress)
    assert len(runner.steps) == 7 and runner.max_actions == 12
    assert "interrompido" in result.response.speech_output


def test_verifier_crash_preserves_uncertainty_about_started_action(tmp_path):
    runner, loop, registry = make_runner(tmp_path, [reply("read_file")])
    calls = []
    registry.register(ToolSpec("read_file", "read"), lambda p: (calls.append(p) or ToolResult(True, "data")))

    def crash(*args):
        raise RuntimeError("verification unavailable")

    loop.verifier.verify = crash
    result = runner.start("Leia")
    assert len(calls) == 1
    assert "resultado não foi confirmado" in result.response.speech_output
