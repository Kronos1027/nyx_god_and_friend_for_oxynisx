"""Nyx AGI Desktop v3 — core/grammar.py (Compilador de JSON Schema para GBNF)

Gera gramáticas GBNF (Grammar-Based Sampling) com cache LRU para constranger
a saída do modelo estritamente às ferramentas permitidas naquele turno,
sem incorrer no "imposto de constrição" na fase de decisão livre.
"""

from __future__ import annotations

import functools
import hashlib
import json
from typing import Any, Dict, List, Tuple


def _json_type_to_gbnf(schema: Dict[str, Any], rule_prefix: str) -> Tuple[str, List[str]]:
    """Converte um nó de JSON Schema para regra GBNF correspondente."""
    stype = schema.get("type", "string")
    rules = []

    if "enum" in schema:
        literals = [f'"\\"{val}\\""' for val in schema["enum"]]
        rule_body = " | ".join(literals)
        rule_name = f"{rule_prefix}-enum"
        rules.append(f"{rule_name} ::= {rule_body}")
        return rule_name, rules

    if stype == "string":
        return "string", []
    elif stype == "integer":
        return "integer", []
    elif stype == "number":
        return "number", []
    elif stype == "boolean":
        return "boolean", []
    elif stype == "array":
        item_schema = schema.get("items", {"type": "string"})
        sub_name, sub_rules = _json_type_to_gbnf(item_schema, f"{rule_prefix}-item")
        rules.extend(sub_rules)
        arr_name = f"{rule_prefix}-array"
        rules.append(f'{arr_name} ::= "[" ws ({sub_name} ("," ws {sub_name})*)? ws "]"')
        return arr_name, rules
    elif stype == "object":
        props = schema.get("properties", {})
        prop_rules = []

        for p_name, p_schema in props.items():
            val_rule, extra_rules = _json_type_to_gbnf(p_schema, f"{rule_prefix}-{p_name}")
            rules.extend(extra_rules)
            p_rule_name = f"{rule_prefix}-prop-{p_name}"
            rules.append(f'{p_rule_name} ::= "\\"\\"{p_name}\\"\\"" ws ":" ws {val_rule}')
            prop_rules.append(p_rule_name)

        obj_name = f"{rule_prefix}-object"
        if prop_rules:
            # Lista de propriedades separadas por vírgula
            props_joined = " ( \",\" ws " + " )? ( \",\" ws ".join(prop_rules) + " )?"
            rules.append(f'{obj_name} ::= "{{" ws {prop_rules[0]} {props_joined} ws "}}"')
        else:
            rules.append(f'{obj_name} ::= "{{}}"')
        return obj_name, rules

    return "value", []


@functools.lru_cache(maxsize=128)
def compile_schema_to_gbnf(schema_json_str: str, root_name: str = "args") -> str:
    """Compila um JSON Schema para GBNF com cache LRU."""
    schema = json.loads(schema_json_str)
    root_rule, sub_rules = _json_type_to_gbnf(schema, root_name)

    base_primitives = """
string  ::= "\\"" ([^"\\\\] | "\\\\" ["\\\\/bfnrt])* "\\""
integer ::= ("-"? [0-9]+)
number  ::= ("-"? [0-9]+ ("." [0-9]+)?)
boolean ::= ("true" | "false")
ws      ::= [ \\t\\n]*
"""
    combined = "\n".join(sub_rules)
    return f"{root_name} ::= {root_rule}\n{combined}\n{base_primitives}".strip()


def grammar_for_turn(allowed_tools: List[Dict[str, Any]]) -> str:
    """Gera gramática restrita para o turno ativo contendo apenas as ferramentas selecionadas."""
    if not allowed_tools:
        # Gramática genérica para resposta de texto livre ou JSON
        return """
root ::= "{" ws "\\"thought\\"" ws ":" ws string ws "," ws "\\"tool\\"" ws ":" ws "\\"final_answer\\"" ws "," ws "\\"args\\"" ws ":" ws "{}" ws "}"
string ::= "\\"" ([^"\\\\] | "\\\\" ["\\\\/bfnrt])* "\\""
ws ::= [ \\t\\n]*
""".strip()

    tool_branches = []
    args_rules = []

    for t in allowed_tools:
        t_name = t.get("name", "tool")
        schema = t.get("schema", {"type": "object"})
        schema_key = hashlib.md5(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:8]
        args_rule_name = f"args-{t_name}-{schema_key}"
        gbnf_snippet = compile_schema_to_gbnf(json.dumps(schema), root_name=args_rule_name)
        args_rules.append(gbnf_snippet)
        branch = f'("{{" ws "\\"thought\\"" ws ":" ws string ws "," ws "\\"tool\\"" ws ":" ws "\\"\\"{t_name}\\"\\"" ws "," ws "\\"args\\"" ws ":" ws {args_rule_name} ws "}}")'
        tool_branches.append(branch)

    branches_combined = " |\n  ".join(tool_branches)
    extra_rules = "\n".join(args_rules)

    return f"""
root ::= {branches_combined}

{extra_rules}
""".strip()
