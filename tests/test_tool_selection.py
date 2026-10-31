from core.tool_selection import select_task_tools


def test_only_explicit_user_delegation_constraint_narrows_catalog():
    tools = [{'name': 'read_file'}, {'name': 'agent_team'}, {'name': 'calculator'}]
    assert [t['name'] for t in select_task_tools('Leia os arquivos. Não delegue.', tools)] == ['read_file', 'calculator']
    assert select_task_tools('Use microagentes para pesquisar.', tools) == tools
    assert select_task_tools('Leia o documento que discute microagentes.', tools) == tools
    assert len(tools) == 3


def test_file_arithmetic_uses_small_catalog_but_mixed_request_preserves_capabilities():
    tools = [{'name': name} for name in ['read_file', 'calculator', 'find_files', 'browser', 'agent_team']]
    assert [t['name'] for t in select_task_tools('Leia oito arquivos e calcule a soma. Não delegue.', tools)] == ['read_file', 'calculator', 'find_files']
    assert select_task_tools('Leia arquivos, calcule a soma e salve o resultado.', tools) == tools
    assert select_task_tools('Use microagentes para ler arquivos e calcular a soma.', tools) == tools
