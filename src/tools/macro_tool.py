"""Nyx — tools/macro_tool.py

Skills gravadas (record & replay) — Fase 1 entrega o STORE funcional:
salvar/listar/replayar sequências de {tool, params} no registry.

A gravação a partir de eventos de UI (Fase 6 completa) pluga neste mesmo
store. Cada macro é um JSON versionável dentro do diretório de macros.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tools.registry import ToolRegistry, ToolResult

MAX_STEPS = 50
MAX_MACRO_BYTES = 64 * 1024
_MACRO_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")


class MacroError(ValueError):
    pass


class MacroStore:
    def __init__(self, macro_dir: Path) -> None:
        self.macro_dir = Path(macro_dir)
        self.macro_dir.mkdir(parents=True, exist_ok=True)

    # -- persistência ------------------------------------------------------

    def _path_for(self, name: str) -> Path:
        if not isinstance(name, str) or not _MACRO_NAME_RE.fullmatch(name):
            raise MacroError(
                f"nome de macro inválido: {name!r} (use [a-z0-9][a-z0-9_-], até 48 chars)"
            )
        return self.macro_dir / f"{name}.json"

    def save(self, name: str, steps: list[dict]) -> Path:
        """Salva macro com steps [{tool, params}]. Valida estrutura mínima."""
        if not isinstance(steps, list) or not (1 <= len(steps) <= MAX_STEPS):
            raise MacroError(f"steps deve ser lista de 1 a {MAX_STEPS} passos")
        clean: list[dict] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or ("tool" not in step and "type" not in step):
                raise MacroError(f"passo {i}: precisa de 'tool' ou 'type' (e 'params')")
            tool = step.get("tool") or step.get("type")
            if not isinstance(tool, str) or not tool:
                raise MacroError(f"passo {i}: 'tool' inválido")
            params = step.get("params", {})
            if not isinstance(params, dict):
                raise MacroError(f"passo {i}: 'params' deve ser objeto")
            clean.append({"tool": tool, "params": params})

        path = self._path_for(name)
        data = json.dumps({"name": name, "steps": clean}, ensure_ascii=False, indent=2)
        if len(data.encode()) > MAX_MACRO_BYTES:
            raise MacroError("macro grande demais")
        path.write_text(data, encoding="utf-8")
        return path

    def load(self, name: str) -> list[dict]:
        path = self._path_for(name)
        if not path.exists():
            raise MacroError(f"macro não existe: {name}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data["steps"])

    def list_macros(self) -> list[str]:
        return sorted(p.stem for p in self.macro_dir.glob("*.json"))

    def delete(self, name: str) -> bool:
        path = self._path_for(name)
        if path.exists():
            path.unlink()
            return True
        return False

    # -- replay --------------------------------------------------------------

    def replay(self, name: str, registry: ToolRegistry) -> list[ToolResult]:
        """Replaya a macro passo a passo via registry (única porta de execução).

        NÃO pula confirmações: se um passo for destrutivo, o replay para
        com resultado de erro pedindo confirmação manual — a macro não
        tem poderes especiais (seção 4.2 vale pra macro também).
        """
        steps = self.load(name)
        results: list[ToolResult] = []
        for i, step in enumerate(steps):
            spec = registry.spec(step["tool"])
            if spec is not None and spec.destructive:
                results.append(ToolResult(
                    ok=False,
                    error=f"passo {i} ({step['tool']}) é destrutivo: "
                          "replay interrompido — confirme manualmente",
                    meta={"macro": name, "step": i, "needs_confirmation": True},
                ))
                break
            results.append(registry.execute(step["tool"], step.get("params", {})))
        return results


def make_macro_tool_func(store: MacroStore, registry: ToolRegistry):
    """Função registrada como ação 'macro_run'.

    params: {"op": "run"|"save"|"list"|"delete", "name": "...", "steps": [...]}
    """

    def _run(params: dict) -> ToolResult:
        op = params.get("op", params.get("action", "run"))
        if op == "list":
            return ToolResult(ok=True,
                              output="\n".join(store.list_macros()) or "(nenhuma macro)",
                              meta={"count": len(store.list_macros())})
        if op == "save":
            path = store.save(params.get("name", ""), params.get("steps", []))
            return ToolResult(ok=True, output=f"macro salva: {path}")
        if op == "delete":
            deleted = store.delete(params.get("name", ""))
            if deleted:
                return ToolResult(ok=True, output=f"macro deletada: {params.get('name')}")
            return ToolResult(ok=False, error=f"macro não encontrada: {params.get('name')}")
        if op == "run":
            results = store.replay(params.get("name", ""), registry)
            lines = [f"[{i}] ok={r.ok} {r.error or r.output[:120]}"
                     for i, r in enumerate(results)]
            ok_all = all(r.ok for r in results)
            return ToolResult(ok=ok_all, output="\n".join(lines),
                              meta={"steps": len(results)})
        return ToolResult(ok=False, error=f"op desconhecida: {op!r}")

    return _run
