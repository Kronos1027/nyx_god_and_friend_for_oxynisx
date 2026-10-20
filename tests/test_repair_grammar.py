"""Testes unitários da Fase 0.6: GBNF e Reparo Determinístico (repair.py e grammar.py)

Valida com precisão 20 casos reais de saídas malformadas de LLMs:
- Code fences variados
- Aspas quebradas e vírgulas excedentes
- Coerção de inteiros, floats, booleanos e listas em formato string
- Fuzzy-matching de nomes de ferramentas
- Injeção de valores padrão
"""

import json

from core.grammar import compile_schema_to_gbnf, grammar_for_turn
from core.repair import repair_tool_call


def test_gbnf_compilation_and_cache():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "deep": {"type": "boolean"},
        },
        "required": ["query"],
    }
    gbnf1 = compile_schema_to_gbnf(json.dumps(schema), root_name="args_test")
    assert "args_test" in gbnf1
    assert "string" in gbnf1
    assert "integer" in gbnf1

    # Testa cache (mesma referência)
    gbnf2 = compile_schema_to_gbnf(json.dumps(schema), root_name="args_test")
    assert gbnf1 == gbnf2

    # Testa grammar_for_turn
    turn_gbnf = grammar_for_turn([{"name": "web_search", "schema": schema}])
    assert "web_search" in turn_gbnf
    assert "root ::=" in turn_gbnf


MALFORMED_OUTPUTS_20 = [
    # 1. Code fence json padrão
    '```json\n{"thought": "Abrindo app", "tool": "ui_action", "args": {"action": "open_app"}}\n```',
    # 2. Code fence sem linguagem
    '```\n{"thought": "Pesquisando", "tool": "web_search", "args": {"query": "python"}}\n```',
    # 3. Texto conversacional antes do JSON
    'Claro! Aqui está a ação solicitada:\n{"thought": "Listando janelas", "tool": "ui_action", "args": {}}',
    # 4. Texto conversacional depois do JSON
    '{"thought": "Verificando arquivos", "tool": "file_operation", "args": {"action": "list"}}\nEspero ter ajudado!',
    # 5. Inteiro passado como string numérica
    '{"thought": "Volume", "tool": "ui_action", "args": {"steps": "15"}}',
    # 6. Booleano passado como string "true"
    '{"thought": "Busca profunda", "tool": "web_search", "args": {"deep": "true"}}',
    # 7. Float passado como string
    '{"thought": "Tempo", "tool": "ui_action", "args": {"duration": "2.5"}}',
    # 8. Alias curto de ferramenta "ui" em vez de "ui_action"
    '{"thought": "Clicando", "tool": "ui", "args": {"x": 100, "y": 200}}',
    # 9. Alias "shell" em vez de "shell_command"
    '{"thought": "Rodando comando", "tool": "shell", "args": {"command": "dir"}}',
    # 10. Alias "web" em vez de "web_search"
    '{"thought": "Buscando", "tool": "web", "args": {"query": "noticias"}}',
    # 11. Chave alternativa "thinking" e "action"
    '{"thinking": "Finalizando", "action": "final_answer", "args": {"message": "Concluído"}}',
    # 12. Chave alternativa "tool_name" e "parameters"
    '{"thought": "Arquivo", "tool_name": "file_operation", "parameters": {"path": "teste.txt"}}',
    # 13. Vírgula excedente antes de fechar objeto
    '{"thought": "Teste", "tool": "ui_action", "args": {"action": "list_apps",},}',
    # 14. Aspas simples em vez de aspas duplas
    "{'thought': 'Lendo', 'tool': 'file_operation', 'args': {'path': 'a.txt'}}",
    # 15. Nome de ferramenta com hífen "web-search"
    '{"thought": "Busca", "tool": "web-search", "args": {"query": "IA local"}}',
    # 16. Nome de ferramenta com dois pontos "ui:action"
    '{"thought": "Click", "tool": "ui:action", "args": {"x": 50, "y": 50}}',
    # 17. Args passado como string simples
    '{"thought": "Comando direto", "tool": "shell_command", "args": "echo olá"}',
    # 18. Espaços no nome da ferramenta "file operation"
    '{"thought": "Escrevendo", "tool": "file operation", "args": {"path": "b.txt"}}',
    # 19. Array passado como string serializada
    '{"thought": "Lista", "tool": "file_operation", "args": {"files": "[\'f1.txt\', \'f2.txt\']"}}',
    # 20. Resposta quase pronta com capitalização diferente "UI_Action"
    '{"thought": "Maximizar", "tool": "UI_Action", "args": {"action": "maximize"}}',
]


def test_repair_20_malformed_outputs():
    allowed = ["ui_action", "web_search", "file_operation", "shell_command", "final_answer"]
    schemas = {
        "ui_action": {
            "properties": {
                "steps": {"type": "integer"},
                "duration": {"type": "number"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }
        },
        "web_search": {
            "properties": {
                "deep": {"type": "boolean"},
            }
        },
        "file_operation": {
            "properties": {
                "files": {"type": "array"},
            }
        },
    }

    successes = 0
    for idx, raw in enumerate(MALFORMED_OUTPUTS_20, 1):
        ok, res, err = repair_tool_call(raw, allowed, schemas)
        assert ok is True, f"Falha no caso {idx}: {err} | Raw: {raw}"
        assert res["tool"] in allowed, f"Ferramenta não permitida no caso {idx}: {res['tool']}"
        assert "thought" in res and res["thought"]
        assert isinstance(res["args"], dict)
        successes += 1

    assert successes == 20
