"""Fase 1 — testes do schema/gramática do LLM (seção 3.3).

Cobre: gramática GBNF existe e define as produções; validate_payload aceita
20 payloads variados; rejeita payloads fora do schema; parse_response cai no
fallback seguro (action none) em qualquer incerteza.
"""

import json
from pathlib import Path

import pytest

from core.llm_client import (
    VALID_ACTION_TYPES,
    VALID_EMOTIONS,
    SchemaValidationError,
    parse_response,
    select_preferred_model,
    validate_payload,
)

REPO = Path(__file__).resolve().parent.parent


def test_model_selection_prefers_newer_local_model_without_download():
    assert select_preferred_model(["qwen2.5:3b-instruct", "qwen3.5:9b"]) == "qwen3.5:9b"
    assert select_preferred_model(["qwen2.5:3b-instruct"]) == "qwen2.5:3b-instruct"
    assert select_preferred_model(["gpt-oss:120b-cloud", "qwen2.5:3b"]) == "qwen2.5:3b"
    assert select_preferred_model(["gpt-oss:120b-cloud"]) is None
    assert select_preferred_model([]) is None


def test_model_routing_respects_measured_size_budget():
    available = ["gemma4:12b", "qwen3.5:9b", "qwen3.5:4b", "qwen2.5:3b-instruct"]
    sizes = {
        "gemma4:12b": 8_100_000_000,
        "qwen3.5:9b": 6_500_000_000,
        "qwen3.5:4b": 3_200_000_000,
        "qwen2.5:3b-instruct": 2_000_000_000,
    }

    assert select_preferred_model(
        available, model_sizes=sizes, max_model_size_bytes=4_000_000_000
    ) == "qwen3.5:4b"


# ---------------------------------------------------------------------------
# Gramática GBNF (arquivo versionado em src/core/schema.gbnf)
# ---------------------------------------------------------------------------

def _grammar_text() -> str:
    return (REPO / "src" / "core" / "schema.gbnf").read_text(encoding="utf-8")


def test_grammar_file_exists_and_defines_root():
    lines = [ln.strip() for ln in _grammar_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert lines, "gramática vazia"
    assert lines[0].startswith("root ::="), "primeira produção deve ser root"
    assert "::=" in "\n".join(lines)


def test_grammar_covers_all_enums():
    # GBNF escapa aspas (\"idle\") — normalizamos removendo backslashes.
    text = _grammar_text().replace("\\", "")
    for e in VALID_EMOTIONS:
        assert f'"{e}"' in text, f"emoção {e} ausente da gramática"
    for a in VALID_ACTION_TYPES:
        assert f'"{a}"' in text, f"action.type {a} ausente da gramática"


def test_grammar_has_required_keys():
    text = _grammar_text().replace("\\", "")
    for key in ("reasoning", "alternative_suggestion", "emotion", "action",
                "requires_confirmation", "confirmation_prompt", "speech_output"):
        assert f'"{key}"' in text, f"chave {key} ausente da gramática"


# ---------------------------------------------------------------------------
# Fábrica de payloads válidos
# ---------------------------------------------------------------------------

def make_payload(**overrides):
    base = {
        "reasoning": "análise curta",
        "alternative_suggestion": None,
        "emotion": "idle",
        "action": {"type": "none", "params": {}},
        "requires_confirmation": False,
        "confirmation_prompt": None,
        "speech_output": "ok",
    }
    base.update(overrides)
    return base


# 20+ payloads variados (definition of done da Fase 1: camada de validação)
VALID_PAYLOADS = [
    make_payload(),
    make_payload(emotion="talk"),
    make_payload(emotion="think"),
    make_payload(emotion="surprised"),
    make_payload(emotion="listening"),
    make_payload(emotion="error"),
    make_payload(emotion="sleep"),
    make_payload(alternative_suggestion="Usar robocopy seria mais rápido."),
    make_payload(action={"type": "shell", "params": {"template": "LIST_DIR", "path": "C:/Users"}}),
    make_payload(action={"type": "read_file", "params": {"path": "nota.txt"}}),
    make_payload(action={"type": "write_file", "params": {"path": "a.txt", "content": "x"}}),
    make_payload(action={"type": "find_files", "params": {"pattern": "*.py"}}),
    make_payload(action={"type": "ui_action", "params": {"target": "botão salvar"}}),
    make_payload(action={"type": "clipboard", "params": {"op": "list"}}),
    make_payload(action={"type": "macro_run", "params": {"op": "run", "name": "backup"}}),
    make_payload(action={"type": "project_status", "params": {"repo": "nyx-agent"}}),
    make_payload(requires_confirmation=True,
                 confirmation_prompt="Deletar arquivo X?", emotion="surprised"),
    make_payload(reasoning="com acentuação e pontuação: ação? sim!", speech_output="Feito."),
    make_payload(action={"type": "shell",
                         "params": {"template": "KILL_PROCESS_BY_NAME", "name": "notepad.exe"}},
                 requires_confirmation=True, emotion="surprised"),
    make_payload(action={"type": "none", "params": {}}, emotion="sleep",
                 speech_output="zzz"),
    make_payload(speech_output="unicode: coração ♥ eEmoji não, mas unicode sim"),
]


@pytest.mark.parametrize("payload", VALID_PAYLOADS, ids=lambda p: p["emotion"] + "-" + p["action"]["type"])
def test_validate_accepts_valid_payloads(payload):
    resp = validate_payload(payload)
    assert resp.emotion == payload["emotion"]
    assert resp.action.type == payload["action"]["type"]
    assert resp.parse_ok is True


# ---------------------------------------------------------------------------
# Rejeições (schema não bate → fallback seguro)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload,why", [
    ({"reasoning": "incompleto"}, "faltam chaves"),
    (make_payload(extra_key="x"), "chave extra"),
    (make_payload(emotion="furiosa"), "emoção inválida"),
    (make_payload(action={"type": "format_disk", "params": {}}), "action.type inválido"),
    (make_payload(action={"type": "shell", "params": [1, 2]}), "params não é objeto"),
    (make_payload(action={"type": "shell"}), "action sem params"),
    (make_payload(requires_confirmation="sim"), "requires_confirmation não-boolean"),
    (make_payload(reasoning=None), "reasoning não-string"),
    (make_payload(action="shell"), "action não-objeto"),
    (make_payload(alternative_suggestion=42), "suggestion não-string/null"),
])
def test_validate_rejects_invalid_payloads(payload, why):
    with pytest.raises(SchemaValidationError):
        validate_payload(payload)


# ---------------------------------------------------------------------------
# parse_response: NUNCA levanta — sempre fallback com action none
# ---------------------------------------------------------------------------

def test_parse_response_garbage_json_falls_back_to_none():
    resp = parse_response("isto não é json {{{")
    assert resp.parse_ok is False
    assert resp.action.type == "none"
    assert resp.parse_error is not None
    assert "json.loads falhou" in resp.parse_error


def test_parse_response_valid_json_wrong_schema_falls_back():
    resp = parse_response(json.dumps({"hello": "world"}))
    assert resp.parse_ok is False
    assert resp.action.type == "none"


def test_parse_response_trailing_text_falls_back():
    resp = parse_response('{"reasoning": "x"} texto solto depois')
    assert resp.parse_ok is False
    assert resp.action.type == "none"


def test_parse_response_happy_path():
    raw = json.dumps(make_payload(speech_output="Entendido"))
    resp = parse_response(raw)
    assert resp.parse_ok is True
    assert resp.speech_output == "Entendido"
    assert resp.action.type == "none"


def test_safe_fallback_never_carries_action():
    resp = parse_response("garbage")
    assert resp.action.type == "none"
    assert resp.action.params == {}
    assert resp.emotion == "error"


def test_parse_response_normalizes_emotion():
    payload = make_payload(speech_output="Sim")
    payload["emotion"] = "thinking"
    resp = parse_response(json.dumps(payload))
    assert resp.parse_ok is True
    assert resp.emotion == "think"


def test_parse_response_normalizes_action_without_params():
    # Caso real do log: {"action": {"type": "none"}}
    raw = '{"reasoning": "r", "speech_output": "ok", "action": {"type": "none"}}'
    resp = parse_response(raw)
    assert resp.parse_ok is True
    assert resp.action.type == "none"
    assert resp.action.params == {}


def test_parse_response_normalizes_colon_keys():
    # Caso real do log: "params:"
    raw = '{"reasoning": "r", "speech_output": "ok", "action": {"type": "ui_action", "params:": {"action": "get_active_window"}}}'
    resp = parse_response(raw)
    assert resp.parse_ok is True
    assert resp.action.type == "ui_action"
    assert resp.action.params == {"action": "get_active_window"}


def test_parse_response_derives_missing_speech_output():
    # Caso real do log: speech_output ausente mas confirmation_prompt presente
    raw = '{"reasoning": "r", "confirmation_prompt": "Confirmar acao?", "action": {"type": "none", "params": {}}}'
    resp = parse_response(raw)
    assert resp.parse_ok is True
    assert resp.speech_output == "Confirmar acao?"
