"""Nyx — tools/file_tool.py

Leitura/escrita/busca de arquivos SANDBOXED (seção 4.3 do prompt mestre):
só opera dentro de diretórios explicitamente permitidos em config.py.

Checagem por `Path.resolve()` + `os.path.commonpath` — cobre `../`, paths
absolutos externos e symlinks que apontem pra fora da sandbox.
"""

from __future__ import annotations

import os
from pathlib import Path

from tools.registry import ToolResult

MAX_READ_BYTES = 2 * 1024 * 1024      # 2MB por leitura
MAX_WRITE_BYTES = 5 * 1024 * 1024     # 5MB por escrita


class SandboxViolation(PermissionError):
    """Tentativa de acesso fora das raízes permitidas (seção 4.3)."""


class FileTool:
    def __init__(self, allowed_roots: list[Path]) -> None:
        if not allowed_roots:
            raise ValueError("pelo menos uma raiz permitida é obrigatória (seção 4.3)")
        self.roots = [Path(r).expanduser().resolve() for r in allowed_roots]
        for r in self.roots:
            r.mkdir(parents=True, exist_ok=True)

    # -- sandbox core ------------------------------------------------------

    def _resolve_sandboxed(self, raw_path: str | Path) -> Path:
        """Resolve o path e garante que está dentro de UMA das raízes.

        Path RELATIVO é resolvido contra a raiz primária (roots[0]) —
        nunca contra o CWD do processo.
        """
        if not isinstance(raw_path, (str, Path)):
            raise SandboxViolation(f"tipo de path inválido: {type(raw_path).__name__}")
        p = Path(raw_path).expanduser()
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (self.roots[0] / p).resolve()
        for root in self.roots:
            try:
                common = os.path.commonpath([str(root), str(resolved)])
            except ValueError:  # drives diferentes no Windows
                continue
            if common == str(root):
                return resolved
        raise SandboxViolation(
            f"{str(raw_path)!r} fora das raízes permitidas "
            f"{[str(r) for r in self.roots]} (seção 4.3)"
        )

    # -- operações ----------------------------------------------------------

    def read_file(self, params: dict) -> ToolResult:
        path = self._resolve_sandboxed(params.get("path", ""))
        if not path.is_file():
            return ToolResult(ok=False, error=f"não é arquivo: {path}")
        size = path.stat().st_size
        if size > MAX_READ_BYTES:
            return ToolResult(ok=False, error=f"arquivo maior que {MAX_READ_BYTES} bytes")
        content = path.read_text(encoding="utf-8", errors="replace")
        return ToolResult(ok=True, output=content, meta={"path": str(path), "size": size})

    def write_file(self, params: dict) -> ToolResult:
        path = self._resolve_sandboxed(params.get("path", ""))
        content = params.get("content", "")
        if not isinstance(content, str):
            return ToolResult(ok=False, error="content deve ser string")
        payload = content.encode("utf-8")
        if len(payload) > MAX_WRITE_BYTES:
            return ToolResult(ok=False, error=f"escrita maior que {MAX_WRITE_BYTES} bytes")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return ToolResult(
            ok=True,
            output=f"escrito: {path} ({len(payload)} bytes)",
            meta={"path": str(path), "size": len(payload)},
        )

    def find_files(self, params: dict) -> ToolResult:
        pattern = params.get("pattern", "*")
        root_raw = params.get("root", str(self.roots[0]))
        root = self._resolve_sandboxed(root_raw)
        if not isinstance(pattern, str) or len(pattern) > 128:
            return ToolResult(ok=False, error="pattern inválido")
        matches = sorted(str(m) for m in list(root.rglob(pattern))[:200])
        return ToolResult(ok=True, output="\n".join(matches), meta={"count": len(matches)})

    def delete_file(self, params: dict) -> ToolResult:
        """DESTRUTIVA — o registry marca destructive=True: o loop SEMPRE
        pede confirmação antes de chegar aqui (seção 4.2, sem exceção)."""
        path = self._resolve_sandboxed(params.get("path", ""))
        if not path.is_file():
            return ToolResult(ok=False, error=f"não é arquivo: {path}")
        path.unlink()
        return ToolResult(ok=True, output=f"deletado: {path}", meta={"path": str(path)})


def make_file_tool_func(tool: FileTool, operation: str):
    """Fábrica de funções registradas no registry (read_file, write_file,
    find_files, delete_file)."""

    ops = {
        "read_file": tool.read_file,
        "write_file": tool.write_file,
        "find_files": tool.find_files,
        "delete_file": tool.delete_file,
    }
    if operation not in ops:
        raise ValueError(f"operação desconhecida: {operation}")
    return ops[operation]
