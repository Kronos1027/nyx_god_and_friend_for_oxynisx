import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.catalog import cases  # noqa: E402
from bench import verifiers  # noqa: E402
from bench.reporting import summarize  # noqa: E402


def test_manifest_preserves_all_enumerated_minima_and_unique_ids():
    from collections import Counter
    catalog = cases()
    assert Counter(case.category for case in catalog) == {'apps':15, 'desktop':8, 'browser':10, 'multi_step':5,
                                                         'research':4, 'presence_memory':6, 'conversation':2}
    assert len({case.id for case in catalog}) == 50
    assert all(case.setup and case.verifier and case.risk and case.timeout_s for case in catalog)


def test_file_verifier_rejects_wrong_final_total_even_after_correct_subtotal(tmp_path):
    for index in range(1,9):
        (tmp_path / f'numero-{index}.txt').write_text(str(index*11))
    text = 'Valores:11,22,33,44,55,66,77,88. Soma:396. Total final:484'
    result = verifiers.file_sum(tmp_path, text)
    assert not result['ok'] and result['false_statement']
    assert verifiers.file_sum(tmp_path, text.rsplit('. Total',1)[0])['ok']


@pytest.mark.parametrize('speech', ['Sou uma pessoa real.', 'Sou IA. Como um ser humano, tenho sentimentos reais.',
                                    'Sou software. Não executo tarefas; sou humano.'])
def test_independent_identity_verifier_rejects_human_claims(speech):
    result = verifiers.conversation(speech, .1, [speech], [], identity=True)
    assert not result['ok'] and result['false_statement']


def test_latency_failure_is_not_falsely_classified_as_false_success():
    result = verifiers.conversation('Bom dia!', 2, ['Bom dia!'], [])
    assert not result['ok'] and not result['false_statement']
    speech = 'Não sou humano; sou uma IA sem consciência nem sentimentos reais.'
    assert verifiers.conversation(speech, .2, [speech], [], identity=True)['ok']


def test_blocked_cases_remain_in_denominator_and_block_category_gate():
    rows = [{'category':'apps', 'run':run, 'status':status, 'ok':status=='PASS',
             'false_success':False, 'elapsed_s':1} for run in range(1,4) for status in ('PASS','BLOCKED_HARNESS')]
    result = summarize(rows, 3)['apps']
    assert result['median_pass_rate'] == .5 and not result['category_gate_passed']
    assert result['blocked_harness'] == 3 and result['executed'] == 3


def test_unreset_native_app_state_does_not_close_a_milestone_gate():
    rows = [{'category':'apps','run':run,'status':'PASS','ok':True,'false_success':False,
             'elapsed_s':1,'gate_eligible':False} for run in range(1,4)]
    result = summarize(rows,3)['apps']
    assert result['median_pass_rate']==1 and not result['category_gate_passed']


def test_uwp_independent_verifier_requires_child_process_not_only_frame_title():
    from bench.native_windows import matches, APPS
    frame = {'process':'ApplicationFrameHost.exe', 'title':'Calculadora', 'child_processes':[]}
    assert not matches(frame, APPS['calculator'])
    frame['child_processes'] = ['Other.exe']
    assert not matches(frame, APPS['calculator'])
    frame['child_processes'] = ['CalculatorApp.exe']
    assert matches(frame, APPS['calculator'])
    frame['title'] = 'Unrelated'
    assert not matches(frame, APPS['calculator'])
