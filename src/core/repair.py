"""Nyx AGI Desktop v3 — core/repair.py (Camada de Reparo Determinístico de Tool-Calls)

Corrige saídas malformadas de LLMs antes de qualquer reprompt:
1. Extração e desembrulho de code fences (```json ... ```) e lixo antes/depois.
2. Coerção determinística de tipos escalares e coleções ("30" -> 30, "true" -> True).
3. Fuzzy-matching de nomes de ferramentas contra o catálogo ativo.
4. Injeção de valores padrão para campos opcionais obrigatórios ausentes.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Dict, List, Optional, Tuple


def extract_json_block(text: str) -> str:
    """Remove markdown code fences, prefixos de conversa e sufixos fora do JSON."""
    text = text.strip()
    # Remove code blocks
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # Busca primeira abertura de chave '{' e último fechamento '}'
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()

    return text


def coerce_value(val: Any, target_type: str) -> Any:
    """Coage strings para tipos primitivos quando o schema assim requer."""
    if val is None:
        return None

    if target_type in ("integer", "int"):
        if isinstance(val, str):
            clean = re.sub(r"[^\d\-]", "", val)
            return int(clean) if clean else 0
        return int(val)

    if target_type in ("number", "float"):
        if isinstance(val, str):
            clean = re.sub(r"[^\d\.\-]", "", val)
            return float(clean) if clean else 0.0
        return float(val)

    if target_type in ("boolean", "bool"):
        if isinstance(val, str):
            return val.strip().lower() in ("true", "1", "yes", "sim", "y")
        return bool(val)

    if target_type in ("array", "list") and isinstance(val, str):
        # Se veio como string de lista ex: "['a', 'b']"
        try:
            parsed = json.loads(val.replace("'", '"'))
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return [val]

    return val


def fuzzy_match_tool(candidate: str, allowed_tools: List[str], cutoff: float = 0.55) -> str:
    """Encontra o nome da ferramenta correspondente mais provável usando fuzzy matching."""
    norm = candidate.strip().lower().replace("-", "_").replace(":", "_").replace(" ", "_")

    # Mapeamentos diretos conhecidos de atalhos comuns
    aliases = {
        "ui": "ui_action",
        "gui": "ui_action",
        "mouse": "ui_action",
        "keyboard": "ui_action",
        "shell": "shell_command",
        "cmd": "shell_command",
        "powershell": "shell_command",
        "bash": "shell_command",
        "terminal": "shell_command",
        "file": "file_operation",
        "fs": "file_operation",
        "search": "web_search",
        "google": "web_search",
        "web": "web_search",
        "answer": "final_answer",
        "done": "final_answer",
    }
    if norm in aliases and aliases[norm] in allowed_tools:
        return aliases[norm]

    # Comparação exata normalizada
    for tool in allowed_tools:
        t_norm = tool.lower().replace("-", "_").replace(":", "_")
        if norm == t_norm:
            return tool

    # Difflib para proximidade de string
    matches = difflib.get_close_matches(norm, allowed_tools, n=1, cutoff=cutoff)
    if matches:
        return matches[0]

    return candidate


def repair_tool_call(
    raw_text: str,
    allowed_tools: List[str],
    schema_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Pipeline completo de reparo determinístico sem chamar outro LLM.

    Retorna: (sucesso, dict_reparado, erro_se_houver)
    """
    cleaned = extract_json_block(raw_text)

    # 1. Parse JSON
    try:
        data = json.loads(cleaned)
    except Exception as exc:
        # Tenta consertar vírgulas sobrando ou aspas simples
        try:
            semi_fixed = re.sub(r",\s*([\]}])", r"\1", cleaned)
            semi_fixed = semi_fixed.replace("'", '"')
            data = json.loads(semi_fixed)
        except Exception:
            return False, {}, f"JSON malformado irrecuperável: {exc}"

    if not isinstance(data, dict):
        return False, {}, "Saída do modelo não é um objeto JSON."

    # 2. Garante chaves mínimas da Nyx
    thought = str(data.get("thought", data.get("thinking", data.get("reason", "Processando ação."))))
    tool_raw = str(data.get("tool", data.get("tool_name", data.get("name", data.get("action", "")))))
    args = data.get("args", data.get("arguments", data.get("parameters", {})))
    if not isinstance(args, dict):
        args = {"value": args} if args is not None else {}

    # 3. Fuzzy match de ferramenta
    matched_tool = fuzzy_match_tool(tool_raw, allowed_tools)

    # 4. Coerção de argumentos com base no schema da ferramenta
    if schema_map and matched_tool in schema_map:
        t_props = schema_map[matched_tool].get("properties", {})
        for prop_name, prop_schema in t_props.items():
            expected_type = prop_schema.get("type")
            if prop_name in args and expected_type:
                args[prop_name] = coerce_value(args[prop_name], expected_type)
            elif "default" in prop_schema and prop_name not in args:
                args[prop_name] = prop_schema["default"]

    repaired = {
        "thought": thought,
        "tool": matched_tool,
        "args": args,
    }

    return True, repaired, None
