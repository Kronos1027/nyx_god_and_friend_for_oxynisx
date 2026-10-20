"""Nyx — llm_client.py

Wrapper do llama.cpp com gramática GBNF (seção 3.1/3.3 do prompt mestre).

Duas camadas de defesa contra saída inválida:
1. Gramática GBNF aplicada em tempo de geração (schema.gbnf) — o modelo
   fisicamente não consegue emitir JSON fora do schema.
2. Validação estrutural em Python pós-parse — se json.loads falhar OU o
   schema não bater, `parse_response` devolve a resposta segura de fallback
   (action.type = "none"), que o agent_loop registra no log de auditoria.

A importação de llama_cpp é LAZY: o núcleo roda e é testado em Linux/CI sem
a lib instalada (ela só existe na máquina Windows de destino).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from core.personality import NYX_SYSTEM_PROMPT

log = logging.getLogger(__name__)

# Newer instruction models are preferred when already installed. Nyx never
# downloads a model implicitly; disk use remains an explicit user choice.
MODEL_PREFERENCE = (
    "qwen3.5:9b",
    "qwen3.5:4b",
    "gemma4:12b-it-q4_K_M",
    "gemma4:12b",
    "qwen2.5:7b-instruct",
    "qwen2.5:7b",
    "qwen2.5:3b-instruct",
    "qwen2.5:3b",
    "deepseek-coder-v2:16b",
    "PetrosStav/gemma3-tools:12b",
    "llama3.2:1b",
)

# Keep a malformed or looping local model response from monopolizing the
# shared GPU/CPU indefinitely. Nyx speaks concisely; 512 tokens still permits
# a substantial structured answer while bounding inference time and memory.
OLLAMA_MAX_OUTPUT_TOKENS = 512


def select_preferred_model(
    models: list[str],
    *,
    model_sizes: dict[str, int] | None = None,
    max_model_size_bytes: int | None = None,
) -> str | None:
    """Pick the strongest installed preference without downloading anything."""
    local_models = [name for name in models if not name.lower().endswith("cloud")]
    if max_model_size_bytes is not None and model_sizes is not None:
        local_models = [
            name for name in local_models
            if 0 < model_sizes.get(name, 0) <= max_model_size_bytes
        ]
    available = set(local_models)
    return next(
        (name for name in MODEL_PREFERENCE if name in available),
        local_models[0] if local_models else None,
    )

# ---------------------------------------------------------------------------
# Constantes do schema (seção 3.3)
# ---------------------------------------------------------------------------

VALID_EMOTIONS = ("idle", "talk", "think", "surprised", "listening", "error", "sleep")

VALID_ACTION_TYPES = (
    "shell", "read_file", "write_file", "find_files", "ui_action",
    "clipboard", "macro_run", "project_status", "workspace", "web", "schedule", "agent_team", "evolution", "none",
)

REQUIRED_KEYS = (
    "reasoning", "alternative_suggestion", "emotion", "action",
    "requires_confirmation", "confirmation_prompt", "speech_output",
)

NYX_JSON_SCHEMA = {
    "type": "object",
    "required": list(REQUIRED_KEYS),
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "alternative_suggestion": {"type": ["string", "null"]},
        "emotion": {"type": "string", "enum": list(VALID_EMOTIONS)},
        "action": {
            "type": "object",
            "required": ["type", "params"],
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": list(VALID_ACTION_TYPES)},
                "params": {"type": "object"},
            },
        },
        "requires_confirmation": {"type": "boolean"},
        "confirmation_prompt": {"type": ["string", "null"]},
        "speech_output": {"type": "string"},
    },
}


class SchemaValidationError(ValueError):
    """Payload parseado mas fora do schema da seção 3.3."""


class BackendUnavailable(RuntimeError):
    """llama_cpp / modelo GGUF não disponíveis neste ambiente."""


# ---------------------------------------------------------------------------
# Estruturas de resposta
# ---------------------------------------------------------------------------

@dataclass
class Action:
    type: str = "none"
    params: dict = field(default_factory=dict)


@dataclass
class NyxResponse:
    """Resposta estruturada do LLM, já validada (ou fallback seguro)."""

    reasoning: str = ""
    alternative_suggestion: str | None = None
    emotion: str = "idle"
    action: Action = field(default_factory=Action)
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    speech_output: str = ""
    raw: str = ""
    parse_ok: bool = True
    parse_error: str | None = None

    @classmethod
    def safe_fallback(cls, raw: str, error: str) -> "NyxResponse":
        """Resposta segura para parse/schema falho: NUNCA executa ação.

        Seção 3.3: "se json.loads falhar OU o schema não bater, a ação é
        none automaticamente e o erro vai pro log de auditoria."
        """
        return cls(
            reasoning="Falha ao interpretar a própria resposta — ação bloqueada.",
            alternative_suggestion=None,
            emotion="error",
            action=Action(type="none", params={}),
            requires_confirmation=False,
            confirmation_prompt=None,
            speech_output="Tive um problema interno ao processar isso. Pode repetir?",
            raw=raw,
            parse_ok=False,
            parse_error=error,
        )


# ---------------------------------------------------------------------------
# Validação estrutural (usada também pelos testes — camada 2 de defesa)
# ---------------------------------------------------------------------------

def validate_payload(data: object) -> NyxResponse:
    """Valida dict já parseado contra o schema da seção 3.3.

    Levanta SchemaValidationError com o motivo exato. Não executa nada.
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(f"payload não é um objeto JSON: {type(data).__name__}")

    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise SchemaValidationError(f"chaves obrigatórias ausentes: {missing}")

    extra = set(data) - set(REQUIRED_KEYS)
    if extra:
        raise SchemaValidationError(f"chaves não previstas no schema: {sorted(extra)}")

    for k in ("reasoning", "speech_output"):
        if not isinstance(data[k], str):
            raise SchemaValidationError(f"'{k}' deve ser string, veio {type(data[k]).__name__}")

    for k in ("alternative_suggestion", "confirmation_prompt"):
        if data[k] is not None and not isinstance(data[k], str):
            raise SchemaValidationError(f"'{k}' deve ser string ou null")

    if data["emotion"] not in VALID_EMOTIONS:
        raise SchemaValidationError(
            f"'emotion' inválida: {data['emotion']!r} (válidas: {VALID_EMOTIONS})"
        )

    if not isinstance(data["requires_confirmation"], bool):
        raise SchemaValidationError(
            f"'requires_confirmation' deve ser boolean, veio {type(data['requires_confirmation']).__name__}"
        )

    action = data["action"]
    if not isinstance(action, dict):
        raise SchemaValidationError(f"'action' deve ser objeto, veio {type(action).__name__}")
    if set(action) != {"type", "params"}:
        raise SchemaValidationError(
            f"'action' deve ter exatamente 'type' e 'params', veio: {sorted(action)}"
        )
    if action["type"] not in VALID_ACTION_TYPES:
        raise SchemaValidationError(
            f"'action.type' inválido: {action['type']!r} (válidos: {VALID_ACTION_TYPES})"
        )
    if not isinstance(action["params"], dict):
        raise SchemaValidationError(
            f"'action.params' deve ser objeto, veio {type(action['params']).__name__}"
        )

    return NyxResponse(
        reasoning=data["reasoning"],
        alternative_suggestion=data["alternative_suggestion"],
        emotion=data["emotion"],
        action=Action(type=action["type"], params=dict(action["params"])),
        requires_confirmation=data["requires_confirmation"],
        confirmation_prompt=data["confirmation_prompt"],
        speech_output=data["speech_output"],
    )


def parse_response(raw: str) -> NyxResponse:
    """Parseia a saída crua do LLM. JAMAIS levanta — fallback seguro sempre.

    Regra de execução da seção 3.3: parse incerto => action.type = "none".
    """
    clean_raw = raw.strip()
    if clean_raw.startswith("```json"):
        clean_raw = clean_raw[7:]
    elif clean_raw.startswith("```"):
        clean_raw = clean_raw[3:]
    if clean_raw.endswith("```"):
        clean_raw = clean_raw[:-3]
    clean_raw = clean_raw.strip()

    try:
        data = json.loads(clean_raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return NyxResponse.safe_fallback(raw, f"json.loads falhou: {exc}")

    if not isinstance(data, dict):
        return NyxResponse.safe_fallback(raw, "payload não é um objeto JSON")

    data = normalize_payload(data)

    try:
        return validate_payload(data)
    except SchemaValidationError as exc:
        return NyxResponse.safe_fallback(raw, f"schema inválido: {exc}")


def normalize_payload(data: dict) -> dict:
    """Normaliza o dicionário vindo do LLM para garantir conformidade estrita com o schema."""
    # Se o objeto não possui nenhuma chave relevante de Nyx, não tenta inventar um payload
    if not any(k in data for k in ("reasoning", "action", "speech_output", "confirmation_prompt", "emotion")):
        return data

    d = dict(data)

    # 1. Normalização de chaves com pontuação (ex: 'params:' -> 'params')
    for k in list(d.keys()):
        clean_k = k.rstrip(":").strip()
        if clean_k != k:
            d[clean_k] = d.pop(k)

    # 2. Normalização de emoções (apenas sinônimos conhecidos; valores ilegais continuam sendo validados)
    if "emotion" in d:
        raw_em = str(d["emotion"]).lower().strip()
        emotion_map = {
            "thinking": "think",
            "thought": "think",
            "curious": "think",
            "speaking": "talk",
            "talking": "talk",
            "contento": "talk",
            "happy": "talk",
            "alegre": "talk",
            "neutral": "idle",
            "sleeping": "sleep",
            "surprised": "surprised",
            "listening": "listening",
            "error": "error",
        }
        if raw_em in emotion_map:
            d["emotion"] = emotion_map[raw_em]

    # 3. Normalização da ação ('action') se for dict
    action = d.get("action")
    if isinstance(action, dict):
        act_dict = {}
        for ak, av in action.items():
            clean_ak = ak.rstrip(":").strip()
            act_dict[clean_ak] = av

        act_type = str(act_dict.get("type", "none")).strip()
        synonyms = {
            "navegador": "web",
            "browser": "web",
            "pesquisa": "web",
        }
        if act_type in synonyms:
            act_type = synonyms[act_type]

        act_params = act_dict.get("params", {})
        if not isinstance(act_params, dict):
            act_params = {}
        d["action"] = {"type": act_type, "params": act_params}

    # 4. Normalização de fala ('speech_output')
    speech = d.get("speech_output")
    if not isinstance(speech, str) or not speech.strip():
        # Deriva fala a partir do prompt de confirmação ou raciocínio
        fallback_speech = d.get("confirmation_prompt") or d.get("reasoning") or "Entendido, procedendo com a operação."
        d["speech_output"] = str(fallback_speech)

    # 5. Garantia de chaves obrigatórias com valores default seguros
    d.setdefault("reasoning", "Análise realizada pelo Grande Sábio.")
    d.setdefault("alternative_suggestion", None)
    d.setdefault("emotion", "idle")
    d.setdefault("requires_confirmation", False)
    d.setdefault("confirmation_prompt", None)

    # 6. Remoção de chaves estranhas não pertencentes ao schema
    clean_d = {k: d[k] for k in REQUIRED_KEYS if k in d}
    return clean_d


# ---------------------------------------------------------------------------
# Cliente real (llama.cpp) — lazy import, só na máquina Windows de destino
# ---------------------------------------------------------------------------

def load_grammar_text(grammar_path: Path) -> str:
    """Carrega e faz um sanity check mínimo da gramática GBNF."""
    text = Path(grammar_path).read_text(encoding="utf-8")
    if "::=" not in text:
        raise ValueError(f"gramática inválida (sem '::='): {grammar_path}")
    if "root" not in text.split("::=", 1)[0]:
        raise ValueError(f"gramática deve definir 'root': {grammar_path}")
    return text


class LLMClient:
    """Wrapper do llama-cpp-python com gramática GBNF obrigatória."""

    def __init__(
        self,
        model_path: Path,
        grammar_path: Path,
        n_gpu_layers: int = -1,
        n_ctx: int = 8192,
        system_prompt: str | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.grammar_path = Path(grammar_path)
        self.grammar_text = load_grammar_text(self.grammar_path)
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        if self.model_path.is_file():
            from core.runtime_budget import admit_gguf_load

            self.n_ctx = admit_gguf_load(self.model_path, n_ctx)
        self.system_prompt = system_prompt or NYX_SYSTEM_PROMPT
        self._llm = None  # carregado sob demanda

    def _ensure_backend(self):
        """Carrega o modelo sob demanda. Levanta BackendUnavailable se falhar."""
        if self._llm is not None:
            return self._llm
        if not self.model_path.is_file():
            raise BackendUnavailable(f"Modelo GGUF não encontrado: {self.model_path}.")
        from core.runtime_budget import admit_gguf_load

        self.n_ctx = admit_gguf_load(self.model_path, self.n_ctx)
        try:
            from llama_cpp import Llama, LlamaGrammar  # import lazy (só no Windows)
        except ImportError as exc:
            raise BackendUnavailable(
                "llama-cpp-python não instalada neste ambiente "
                f"({exc}) — esperado fora da máquina Windows alvo."
            ) from exc

        self._grammar = LlamaGrammar.from_string(self.grammar_text)
        self._llm = Llama(
            model_path=str(self.model_path),
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            verbose=False,
        )
        return self._llm

    def generate(self, user_input: str, history: list[dict] | None = None) -> str:
        """Gera resposta crua já constrangida pela gramática GBNF."""
        from core.runtime_budget import INFERENCE_GATE, ensure_resource_headroom, resource_snapshot

        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        with INFERENCE_GATE.slot():
            ensure_resource_headroom(resource_snapshot())
            llm = self._ensure_backend()
            out = llm.create_chat_completion(
                messages=messages,
                grammar=self._grammar,
                max_tokens=OLLAMA_MAX_OUTPUT_TOKENS,
                temperature=0.2,
            )
        return str(out["choices"][0]["message"]["content"])


class OfflineLLM:
    """LLM determinístico de desenvolvimento/testes (NÃO é o modelo real).

    Usado pelo CLI --offline e pelos testes do agent_loop para exercitar o
    ciclo completo (parse -> validação -> ação -> auditoria) sem GPU/modelo.
    Deixando explícito: isto não valida o comportamento do Qwen2.5 —
    isso só acontece na máquina Windows (ver STATUS.md).
    """

    def __init__(self, scripted: list[str] | None = None, unavailable_reason: str = "") -> None:
        self._scripted = list(scripted or [])
        self.received: list[str] = []
        self.unavailable_reason = unavailable_reason

    def queue(self, raw: str) -> None:
        self._scripted.append(raw)

    def generate(self, user_input: str, history: list[dict] | None = None) -> str:
        self.received.append(user_input)
        if self._scripted:
            return self._scripted.pop(0)
        # Resposta padrão: sem ação, apenas fala.
        return json.dumps({
            "reasoning": "Sem ferramenta adequada para este pedido.",
            "alternative_suggestion": None,
            "emotion": "idle",
            "action": {"type": "none", "params": {}},
            "requires_confirmation": False,
            "confirmation_prompt": None,
            "speech_output": (
                f"Estou sem modelo de linguagem ativo. {self.unavailable_reason}"
                if self.unavailable_reason else "Ainda não sei fazer isso. Me diga mais?"
            ),
        }, ensure_ascii=False)


class OllamaClient:
    """Cliente para servidor local Ollama (ex: Qwen2.5, DeepSeek)."""

    def __init__(
        self,
        model: str = "qwen2.5:3b-instruct",
        host: str | None = None,
        system_prompt: str | None = None,
        timeout: float = 60.0,
        keep_alive: str = "5m",
    ) -> None:
        self.model = model
        self.host = (host or os.environ.get("NYX_OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.system_prompt = system_prompt or NYX_SYSTEM_PROMPT

    def is_available(self) -> bool:
        """Verifica rapidamente se o Ollama está acessível."""
        import urllib.request
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as res:
                return res.status == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Lista modelos baixados no Ollama."""
        import urllib.request
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as res:
                data = json.loads(res.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    def list_model_inventory(self) -> list[dict[str, int | str]]:
        """Return installed model names and disk sizes for memory-aware routing."""
        import urllib.request

        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as res:
                data = json.loads(res.read().decode("utf-8"))
            return [
                {"name": str(model.get("name", "")), "size": int(model.get("size", 0))}
                for model in data.get("models", [])
                if model.get("name")
            ]
        except Exception:
            return []

    def generate(self, user_input: str, history: list[dict] | None = None, memory_context: str | None = None) -> str:
        """Envia prompt ao Ollama e retorna o JSON gerado."""
        sys_content = self.system_prompt
        if memory_context:
            sys_content += f"\n\n{memory_context}"

        messages = [{"role": "system", "content": sys_content}]
        if history:
            for h in history:
                role = "user" if h.get("role") == "user" else "assistant"
                content = h.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_input})

        payload = {
            "model": self.model,
            "messages": messages,
            "format": NYX_JSON_SCHEMA,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,
                "num_predict": OLLAMA_MAX_OUTPUT_TOKENS,
            },
            "stream": False,
        }

        try:
            from core.runtime_budget import post_ollama_json

            res_data = post_ollama_json(f"{self.host}/api/chat", payload, self.timeout)
            return res_data.get("message", {}).get("content", "")
        except Exception as exc:
            log.error(f"Erro na requisição ao Ollama ({self.host}): {exc}")
            raise BackendUnavailable(f"Falha no runtime local: {exc}") from exc


def create_llm_client(
    model_arg: str | None = None,
    offline: bool = False,
    cfg=None,
) -> tuple[object, str]:
    """Auto-detecta e instancia o melhor backend disponível.

    Retorna (cliente_llm, nome_do_backend).
    """
    if offline:
        return OfflineLLM(), "offline"

    # 1. Se usuário passou caminho explícito de arquivo GGUF
    if model_arg and Path(model_arg).is_file():
        try:
            grammar_path = cfg.grammar_path if cfg else Path("src/core/schema.gbnf")
            n_gpu = cfg.n_gpu_layers if cfg else -1
            n_ctx = cfg.n_ctx if cfg else 8192
            return LLMClient(Path(model_arg), grammar_path, n_gpu_layers=n_gpu, n_ctx=n_ctx), f"llama_cpp:{model_arg}"
        except Exception as e:
            log.warning(f"Falha ao carregar GGUF {model_arg}: {e}")

    # 2. Testa Ollama local
    ollama = OllamaClient()
    if ollama.is_available():
        inventory = ollama.list_model_inventory()
        models = [str(item["name"]) for item in inventory]
        log.info(f"Ollama detectado com modelos: {models}")
        sizes = {str(item["name"]): int(item["size"]) for item in inventory}
        from core.runtime_budget import GIB, model_weight_budget_bytes, resource_snapshot

        max_size = model_weight_budget_bytes(resource_snapshot())
        if max_size is None:
            max_size = 4 * GIB
        chosen = select_preferred_model(
            models, model_sizes=sizes, max_model_size_bytes=max_size
        )

        if chosen:
            ollama.model = chosen
            return ollama, f"ollama:{chosen}"
        if models:
            log.warning(
                "Nenhum modelo Ollama cabe no orçamento conservador atual (%d MiB); "
                "Nyx não vai carregá-lo automaticamente.",
                max_size // (1024 * 1024),
            )

    # 3. Testa GGUF local em caminhos conhecidos
    candidate_paths = [
        Path("models/qwen2.5-7b-instruct-q5_k_m.gguf"),
    ]
    if cfg and getattr(cfg, "model_path", None):
        candidate_paths.insert(0, Path(cfg.model_path))

    for cand in candidate_paths:
        if cand.exists():
            try:
                grammar_path = cfg.grammar_path if cfg else Path("src/core/schema.gbnf")
                n_gpu = cfg.n_gpu_layers if cfg else -1
                n_ctx = cfg.n_ctx if cfg else 8192
                return LLMClient(cand, grammar_path, n_gpu_layers=n_gpu, n_ctx=n_ctx), f"llama_cpp:{cand.name}"
            except Exception as e:
                log.warning(f"Falha ao carregar GGUF {cand}: {e}")

    # 4. Fallback seguro para desenvolvimento
    log.warning("Nenhum backend real (Ollama ou GGUF) disponível. Usando OfflineLLM.")
    return OfflineLLM(unavailable_reason="Nenhum modelo local disponível cabe no orçamento atual ou pôde ser iniciado. Verifique Ollama e a memória livre."), "offline_fallback"
