"""Nyx AGI Desktop v3 — core/backend.py (Abstração de Runtime de Inferência)

Implementa o protocolo LLMBackend para unificar:
- LlamaCppBackend (llama-server local via HTTP / REST, suporte GBNF e slots)
- OllamaBackend (Ollama local fallback via /api/chat)
Nenhum módulo do agente chama HTTP diretamente sem passar por este protocolo.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

log = logging.getLogger(__name__)


@dataclass
class BackendCaps:
    grammar: bool = False
    logprobs: bool = False
    prefix_cache: bool = True
    vision: bool = False
    parallel_slots: int = 1


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: Dict[str, Any]


@dataclass
class Completion:
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_s: float = 0.0


@runtime_checkable
class LLMBackend(Protocol):
    """Protocolo unificado para execução de LLMs locais."""

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        grammar: Optional[str] = None,
        tools: Optional[List[ToolSpec]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        stop: Optional[List[str]] = None,
    ) -> Completion:
        """Executa a conclusão do chat com gramática opcional ou ferramentas."""
        ...

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Gera representação vetorial (embeddings) para a lista de textos."""
        ...

    def capabilities(self) -> BackendCaps:
        """Informa capacidades técnicas do runtime."""
        ...


class LlamaCppBackend:
    """Backend nativo para llama-server (llama.cpp)."""

    def __init__(self, endpoint: str = "http://127.0.0.1:8080", timeout: float = 40.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        grammar: Optional[str] = None,
        tools: Optional[List[ToolSpec]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        stop: Optional[List[str]] = None,
    ) -> Completion:
        url = f"{self.endpoint}/v1/chat/completions"
        payload: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if grammar:
            payload["grammar"] = grammar
        if stop:
            payload["stop"] = stop

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return Completion(
                content=content,
                raw_response=data,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
        except Exception as exc:
            log.error("Erro na chamada ao LlamaCppBackend (%s): %s", url, exc)
            raise

    def embed(self, texts: List[str]) -> List[List[float]]:
        url = f"{self.endpoint}/v1/embeddings"
        payload = {"input": texts}
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [item["embedding"] for item in data.get("data", [])]

    def capabilities(self) -> BackendCaps:
        return BackendCaps(grammar=True, logprobs=True, prefix_cache=True, vision=False, parallel_slots=2)


class OllamaBackend:
    """Backend para Ollama local (fallback estável na porta 11434)."""

    def __init__(
        self,
        endpoint: str | None = None,
        model: str = "qwen2.5:3b-instruct",
        timeout: float = 40.0,
    ) -> None:
        self.endpoint = (
            endpoint or os.environ.get("NYX_OLLAMA_HOST", "http://127.0.0.1:11434")
        ).rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        grammar: Optional[str] = None,
        tools: Optional[List[ToolSpec]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        stop: Optional[List[str]] = None,
    ) -> Completion:
        url = f"{self.endpoint}/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if stop:
            payload["options"]["stop"] = stop

        # Se tools for passado, converte para schemas json compatíveis
        if tools:
            ollama_tools = []
            for t in tools:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.schema,
                    },
                })
            payload["tools"] = ollama_tools

        try:
            from core.runtime_budget import post_ollama_json

            data = post_ollama_json(url, payload, self.timeout)
            msg = data.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            p_toks = data.get("prompt_eval_count", 0)
            c_toks = data.get("eval_count", 0)
            return Completion(
                content=content,
                tool_calls=tool_calls,
                raw_response=data,
                prompt_tokens=p_toks,
                completion_tokens=c_toks,
            )
        except Exception as exc:
            log.error("Erro na chamada ao OllamaBackend (%s): %s", url, exc)
            raise

    def embed(self, texts: List[str]) -> List[List[float]]:
        url = f"{self.endpoint}/api/embed"
        payload = {"model": self.model, "input": texts}
        from core.runtime_budget import post_ollama_json

        data = post_ollama_json(url, payload, self.timeout)
        return data.get("embeddings", [])

    def capabilities(self) -> BackendCaps:
        return BackendCaps(grammar=False, logprobs=False, prefix_cache=True, vision=True, parallel_slots=1)
