"""Nyx — tools/shell_tool.py

Execução de comandos via allowlist de templates parametrizados
(seção 4.2 do prompt mestre — não-negociável):

- NUNCA repassa string livre do LLM pro subprocess.
- Comandos permitidos vêm de TEMPLATES com validação de parâmetros.
- Fora da allowlist -> ShellBlockedError -> o loop trata como
  requires_confirmation (mesmo em modo autônomo).
- Destrutivos (KILL_PROCESS_BY_NAME etc.) -> flagged destructive:
  confirmação SEMPRE, mesmo em modo autônomo.

Dois dialetos suportados:
- "posix" (dev/testes no Linux/CI): lista de args SEM shell=True.
- "powershell" (Windows alvo): script PS único via powershell -Command.

Os dialetos existem pra que a lógica de allowlist/validação seja testada
de verdade no CI Linux; a validação no Windows real fica pendurada no
STATUS.md até ser executada na máquina alvo.
"""

from __future__ import annotations

import re
import subprocess  # noqa: S404 — só executa templates allowlisted com args validados
from typing import Callable

from tools.registry import ToolResult


class ShellBlockedError(RuntimeError):
    """Comando/params bloqueados pela camada de allowlist."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"bloqueado ({reason}): {detail}")
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------------------
# Validação de parâmetros
# ---------------------------------------------------------------------------

# Caracteres que permitem escape de contexto ou encadeamento.
# Obs.: aspas simples/trasgadas são proibidas porque o dialeto powershell
# interpola params dentro de strings single-quoted; aspas duplas viram
# injeção de sintaxe. Backslash é PERMITIDO em paths (C:\Users\...).
_FORBIDDEN_CHARS = set(';|&`$\n\r<>!"\'')

_FORBIDDEN_SUBSTRINGS = ("..", "$(", "${", "%(", "&&", "||")

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-\.@\[\]]{1,64}$")
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_\-\. /:\\]{1,260}$")
_SAFE_INT_RE = re.compile(r"^-?\d{1,9}$")


def validate_param(kind: str, name: str, value: object) -> str:
    """Valida um parâmetro por tipo. Retorna valor como string sanitizada.

    kind: "path" | "name" | "int"
    Levanta ShellBlockedError em qualquer sinal de escape/injection/traversal.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        s = str(value)
    elif isinstance(value, str):
        s = value
    else:
        raise ShellBlockedError("param_tipo", f"{name}: tipo inaceitável {type(value).__name__}")

    if kind == "int":
        if not _SAFE_INT_RE.fullmatch(s):
            raise ShellBlockedError("param_invalido", f"{name}: inteiro suspeito {s!r}")
        return s

    if any(c in _FORBIDDEN_CHARS for c in s):
        raise ShellBlockedError("param_caractere_proibido",
                                f"{name}: caractere perigoso em {s!r}")
    for sub in _FORBIDDEN_SUBSTRINGS:
        if sub in s:
            raise ShellBlockedError("param_seq_proibida", f"{name}: sequência {sub!r} em {s!r}")

    # Argument injection: nenhum param pode começar com '-' (viraria flag).
    if s.startswith("-"):
        raise ShellBlockedError("param_invalido", f"{name}: não pode começar com '-'")

    if kind == "name":
        if not _SAFE_NAME_RE.fullmatch(s):
            raise ShellBlockedError("param_invalido", f"{name}: nome fora do padrão {s!r}")
    elif kind == "path":
        if not _SAFE_PATH_RE.fullmatch(s):
            raise ShellBlockedError("param_invalido", f"{name}: path fora do padrão {s!r}")
        if "//" in s or "::" in s:
            raise ShellBlockedError("param_invalido", f"{name}: path suspeito {s!r}")
    else:
        raise ShellBlockedError("param_kind", f"kind desconhecido: {kind!r}")

    return s


# ---------------------------------------------------------------------------
# Templates da allowlist
# ---------------------------------------------------------------------------

# builder: Callable[[dict, str], list[str] | str]
#   recebe (params sanitizados, dialect) e devolve:
#   - posix      -> lista de args (subprocess SEM shell=True)
#   - powershell -> string de script PS

class ShellTemplate:
    """Um template parametrizado da allowlist (seção 4.2)."""

    def __init__(
        self,
        name: str,
        description: str,
        builder: Callable[[dict, str], "list[str] | str"],
        params: dict[str, str] | None = None,
        optional_params: dict[str, str] | None = None,
        destructive: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.builder = builder
        self.params = dict(params or {})
        self.optional_params = dict(optional_params or {})
        self.destructive = destructive


_TEMPLATES: dict[str, ShellTemplate] = {}


def _template(t: ShellTemplate) -> ShellTemplate:
    _TEMPLATES[t.name] = t
    return t


_template(ShellTemplate(
    name="LIST_DIR",
    description="Lista arquivos de um diretório.",
    builder=lambda p, d: (
        ["ls", "-la", p["path"]] if d == "posix"
        else f"Get-ChildItem -Force -LiteralPath '{p['path']}'"
    ),
    params={"path": "path"},
))

_template(ShellTemplate(
    name="GET_FILE_INFO",
    description="Mostra tamanho/data de um arquivo.",
    builder=lambda p, d: (
        ["stat", p["path"]] if d == "posix"
        else f"Get-Item -LiteralPath '{p['path']}' | Format-List Name,Length,LastWriteTime"
    ),
    params={"path": "path"},
))

_template(ShellTemplate(
    name="GET_PROCESS",
    description="Lista processos (filtro opcional por nome, aplicado pós-execução).",
    builder=lambda p, d: (
        (["ps", "aux"] if d == "posix" else "Get-Process")
        if "name" not in p
        else (
            ["ps", "aux"]
            if d == "posix"
            else f"Get-Process -Name '{p['name']}'"
        )
    ),
    params={},
    optional_params={"name": "name"},
))

_template(ShellTemplate(
    name="DISK_FREE",
    description="Mostra espaço livre em disco.",
    builder=lambda p, d: (
        ["df", "-h"] if d == "posix"
        else "Get-PSDrive -PSProvider FileSystem | "
             "Select-Object Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}"
    ),
    params={},
))

_template(ShellTemplate(
    name="KILL_PROCESS_BY_NAME",
    description="Encerra processos pelo nome — DESTRUTIVO: sempre pede confirmação.",
    builder=lambda p, d: (
        ["pkill", "-f", p["name"]] if d == "posix"
        else f"Stop-Process -Name '{p['name']}' -Force"
    ),
    params={"name": "name"},
    destructive=True,
))

_template(ShellTemplate(
    name="DELETE_FILE",
    description="Deleta um arquivo — DESTRUTIVO: sempre pede confirmação, "
                "mesmo em modo autônomo (seção 4.2, sem exceção).",
    builder=lambda p, d: (
        ["rm", "--", p["path"]] if d == "posix"
        else f"Remove-Item -LiteralPath '{p['path']}' -Force"
    ),
    params={"path": "path"},
    destructive=True,
))


# ---------------------------------------------------------------------------
# A ferramenta
# ---------------------------------------------------------------------------

class ShellTool:
    """Executa SOMENTE templates da allowlist, com params validados."""

    def __init__(self, dialect: str = "posix", timeout: int = 20) -> None:
        if dialect not in ("posix", "powershell"):
            raise ValueError(f"dialeto inválido: {dialect}")
        self.dialect = dialect
        self.timeout = timeout

    # -- API de introspecção -------------------------------------------

    def template_names(self) -> list[str]:
        return sorted(_TEMPLATES)

    def is_destructive(self, template_name: str) -> bool:
        t = _TEMPLATES.get(template_name)
        return bool(t and t.destructive)

    def preview_command(self, template_name: str, params: dict) -> str:
        """Comando exato que seria executado (para exibir no dialog de
        confirmação — seção 4.2: 'exibição do comando exato antes de rodar')."""
        t = _TEMPLATES.get(template_name)
        if t is None:
            raise ShellBlockedError("fora_da_allowlist", f"template {template_name!r} não existe")
        clean = self._validate_params(t, params)
        command = t.builder(clean, self.dialect)
        if isinstance(command, list):
            return " ".join(command)
        return str(command)

    # -- núcleo ----------------------------------------------------------

    def _validate_params(self, t: ShellTemplate, params: dict) -> dict[str, str]:
        declared = dict(t.params)
        optional = getattr(t, "optional_params", {})
        allowed = set(declared) | set(optional)
        extras = set(params) - allowed
        if extras:
            raise ShellBlockedError("param_nao_declarado", f"extras: {sorted(extras)}")
        missing = set(declared) - set(params)
        if missing:
            raise ShellBlockedError("param_faltando", f"faltando: {sorted(missing)}")
        all_specs = {**declared, **optional}
        return {k: validate_param(all_specs[k], k, v) for k, v in params.items()}

    def run_template(self, template_name: str, params: dict) -> ToolResult:
        """Resolve template + valida params + executa subprocess seguro."""
        t = _TEMPLATES.get(template_name)
        if t is None:
            raise ShellBlockedError(
                "fora_da_allowlist",
                f"{template_name!r} não está na allowlist — exige confirmação com "
                "o comando exato antes de rodar (seção 4.2)",
            )

        clean = self._validate_params(t, params)
        command = t.builder(clean, self.dialect)

        if self.dialect == "posix":
            if not isinstance(command, list):
                raise ShellBlockedError("template_bug",
                                        f"{template_name}: posix deve retornar lista de args")
            argv = command  # lista de args — NUNCA shell=True
        else:  # powershell (Windows alvo)
            # Forçar UTF-8 no output do PS para evitar UnicodeDecodeError
            # com locales pt-BR (cp1252 por padrão).
            ps_cmd = (
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "[Console]::InputEncoding  = [System.Text.Encoding]::UTF8; "
                f"{command}"
            )
            argv = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd]

        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=self.timeout, shell=False, check=False,
        )

        ok = proc.returncode == 0
        return ToolResult(
            ok=ok,
            output=(proc.stdout or "").strip(),
            error=None if ok else (proc.stderr or f"exit={proc.returncode}").strip(),
            meta={
                "template": template_name,
                "dialect": self.dialect,
                "argv": argv if isinstance(argv, list) else [str(command)],
                "destructive": t.destructive,
            },
        )


# ---------------------------------------------------------------------------
# Adaptador para o registry (ação "shell")
# ---------------------------------------------------------------------------

def make_shell_tool_func(tool: ShellTool):
    """Fábrica da função registrada como ação 'shell'.

    O LLM envia params={"template": "...", **args}. O template é a porta
    de entrada da allowlist; qualquer coisa fora dela é bloqueada.
    """

    def _run(params: dict) -> ToolResult:
        template_name = params.get("template")
        if not isinstance(template_name, str) or not template_name:
            return ToolResult(
                ok=False, error="bloqueado (param_faltando): params.template é obrigatório",
                meta={"blocked": True, "reason": "param_faltando"},
            )
        args = {k: v for k, v in params.items() if k != "template"}
        try:
            return tool.run_template(template_name, args)
        except ShellBlockedError as exc:
            return ToolResult(ok=False, error=str(exc),
                              meta={"blocked": True, "reason": exc.reason})

    return _run
