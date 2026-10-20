"""Nyx — tools/clipboard_tool.py (Fase 6: Produtividade - Clipboard)

Histórico e manipulação segura da Área de Transferência (Clipboard) do Windows.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone

from tools.registry import ToolResult

log = logging.getLogger(__name__)


class ClipboardTool:
    """Gerenciamento de leitura, escrita e histórico da área de transferência."""

    def __init__(self, max_history: int = 50) -> None:
        self.max_history = max_history
        self._history: deque[dict] = deque(maxlen=max_history)

    def read_clipboard(self, params: dict | None = None) -> ToolResult:
        """Lê o conteúdo textual atual da área de transferência."""
        try:
            import pyperclip

            text = pyperclip.paste() or ""
            if text and (not self._history or self._history[-1]["content"] != text):
                self._record(text)

            preview = text[:500] + ("..." if len(text) > 500 else "")
            return ToolResult(
                ok=True,
                output=text if text else "(Área de transferência está vazia)",
                meta={"length": len(text), "preview": preview},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao ler clipboard: {exc}")

    def write_clipboard(self, params: dict) -> ToolResult:
        """Copia texto para a área de transferência."""
        text = params.get("text", params.get("content", ""))
        if not isinstance(text, str):
            return ToolResult(ok=False, error="Parâmetro 'text' deve ser uma string.")

        try:
            from tools.clipboard_io import copy_text

            copy_text(text)
            self._record(text)
            preview = text[:100] + ("..." if len(text) > 100 else "")
            return ToolResult(
                ok=True,
                output=f"Copiado para o clipboard ({len(text)} caracteres): '{preview}'",
                meta={"length": len(text)},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao escrever no clipboard: {exc}")

    def get_history(self, params: dict | None = None) -> ToolResult:
        """Retorna os últimos itens copiados."""
        params = params or {}
        limit = int(params.get("limit", 10))
        items = list(self._history)[-limit:]
        if not items:
            return ToolResult(
                ok=True, output="Nenhum item gravado no histórico da sessão.", meta={"count": 0}
            )

        formatted = []
        for i, item in enumerate(reversed(items), 1):
            ts = item["timestamp"]
            prev = item["content"][:80].replace("\n", " ")
            formatted.append(f"{i}. [{ts}] {prev}")

        return ToolResult(
            ok=True,
            output="\n".join(formatted),
            meta={"count": len(items)},
        )

    def clear(self, params: dict | None = None) -> ToolResult:
        """Limpa a área de transferência."""
        try:
            from tools.clipboard_io import copy_text

            copy_text("")
            return ToolResult(ok=True, output="Área de transferência limpa.")
        except Exception as exc:
            return ToolResult(ok=False, error=f"Falha ao limpar clipboard: {exc}")

    def _record(self, text: str) -> None:
        if not text.strip():
            return
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._history.append({"timestamp": ts, "content": text})

    def run(self, params: dict) -> ToolResult:
        """Despacha a ação de clipboard."""
        action = params.get("action", params.get("op", "read")).lower()
        dispatch = {
            "read": self.read_clipboard,
            "get": self.read_clipboard,
            "paste": self.read_clipboard,
            "write": self.write_clipboard,
            "set": self.write_clipboard,
            "copy": self.write_clipboard,
            "history": self.get_history,
            "clear": self.clear,
        }
        handler = dispatch.get(action)
        if not handler:
            return ToolResult(
                ok=False,
                error=f"Ação de clipboard desconhecida: '{action}'. Ações válidas: {list(dispatch.keys())}",
            )
        return handler(params)


def make_clipboard_tool_func(tool: ClipboardTool):
    """Fábrica para ação 'clipboard' do registry."""

    def _run(params: dict) -> ToolResult:
        return tool.run(params)

    return _run
