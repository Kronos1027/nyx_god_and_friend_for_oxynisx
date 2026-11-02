import pytest

from core.app_grounding import explicit_app_issue, explicit_app_target
from core.tool_selection import select_task_tools


@pytest.mark.parametrize('goal', ['Abre a calculadora.', 'Abra o Bloco de notas', 'Abre o Paint',
                                   'Abre o Explorador de Arquivos', 'Abre o Gerenciador de Tarefas'])
def test_launch_catalog_cannot_substitute_arithmetic_or_web(goal):
    tools = [{'name':name} for name in ('ui_action','calculator','browser','shell')]
    assert explicit_app_target(goal)
    assert select_task_tools(goal, tools) == [{'name':'ui_action'}]
    assert explicit_app_issue(goal, 'calculator', {'operation':'sum','values':[1,2]})
    assert explicit_app_issue(goal, 'none', {})


def test_opening_requires_correct_target_and_verified_window_before_completion():
    goal = 'Abre a calculadora.'
    assert explicit_app_issue(goal, 'ui_action', {'action':'open_app','app':'Paint'})
    assert explicit_app_issue(goal, 'ui_action', {'action':'open_url','url':'https://example.test'})
    assert not explicit_app_issue(goal, 'ui_action', {'action':'open_app','app':'calc.exe'})
    step = {'tool':'ui_action','params':{'action':'open_app','app':'Calculator'},'verified':False}
    assert explicit_app_issue(goal, 'none', {}, [step])
    step['verified'] = True
    assert not explicit_app_issue(goal, 'none', {}, [step])


def test_explanation_and_multi_intent_are_not_rewritten_as_simple_opening():
    for goal in ('Explique como abrir a calculadora sem fazer isso.',
                 'Abra a calculadora e leia o arquivo.', 'Calcule 2+2.'):
        assert not explicit_app_target(goal)
        assert not explicit_app_issue(goal, 'none', {})
