from types import SimpleNamespace

from core.arithmetic_grounding import calculator_issue, final_sum_issue, source_issue

GOAL = 'Leia os arquivos e calcule a soma.'


def read(path, value):
    return {'tool': 'read_file', 'ok': True, 'verified': True,
            'params': {'path': path}, 'output': str(value)}


def test_duplicate_read_is_not_an_extra_operand_but_equal_values_in_two_files_are():
    steps = [read('one.txt', 22), read('./one.txt', 22), read('two.txt', 22)]
    assert calculator_issue(GOAL, steps, 'calculator', {'values': [22, 22]}) is None
    assert calculator_issue(GOAL, steps, 'calculator', {'values': [22, 22, 22]})
    assert calculator_issue(GOAL, steps, 'calculator', {'values': [44, 22]})
    assert calculator_issue(GOAL, steps, 'calculator', {'operation': 'product', 'values': [22, 22]})


def test_wrong_final_total_is_rejected_against_observed_calculator_output():
    steps = [read('a.txt', 11), read('b.txt', 22),
             {'tool': 'calculator', 'ok': True, 'verified': True,
              'params': {'operation': 'sum', 'values': [11, 22]}, 'output': '{"result":"33"}'}]
    response = SimpleNamespace(action=SimpleNamespace(type='none'), speech_output='O valor total é 55.')
    assert final_sum_issue(GOAL, steps, response)
    response.speech_output = 'A soma total é 33.'
    assert final_sum_issue(GOAL, steps, response) is None


def test_nonnumeric_or_mixed_tasks_do_not_receive_unjustified_operand_constraints():
    assert calculator_issue(GOAL, [read('a.txt', 'not a number')], 'calculator', {'values': [1]}) is None
    assert calculator_issue('Leia arquivos e calcule soma e média.', [read('a.txt', 1)],
                            'calculator', {'operation': 'mean', 'values': [1]}) is None


def test_explicit_file_interval_rejects_invented_ninth_file_without_restricting_other_requests():
    goal = 'Leia arquivos numero-1.txt até numero-8.txt e entregue a soma.'
    assert source_issue(goal, [], 'read_file', {'path': 'numero-9.txt'})
    assert source_issue(goal, [], 'read_file', {'path': 'numero-8.txt'}) is None
    assert source_issue('Leia os arquivos e entregue a soma.', [], 'read_file', {'path': 'numero-9.txt'}) is None
    assert source_issue('Leia arquivos a-1.txt até b-8.txt e entregue a soma.', [], 'read_file', {'path': 'numero-9.txt'}) is None
