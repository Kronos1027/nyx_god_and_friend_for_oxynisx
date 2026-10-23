"""Nyx — core/verifier.py (Fase 1: Módulo Verifier e Taxonomia de Falhas)

Implementa a regra de ouro da AGI: NUNCA dizer "feito" sem verificar.
Toda ação executada é verificada empiricamente contra o estado real do Windows:
- Processo/Janela abriu? (psutil / pygetwindow)
- Arquivo foi gravado com tamanho > 0 bytes? (Path.stat)
- Saída é válida e não-vazia?
- Houve erro de sistema?

Taxonomia de Falhas:
- CommandNotFound: aplicativo ou comando não existe no PATH/sistema.
- PermissionDenied: acesso negado ou restrição do SO/UAC.
- WindowNotFound: janela alvo não foi encontrada para foco ou clique.
- Timeout: operação excedeu o tempo limite.
- InvalidOutput: retorno vazio ou corrompido.
- NetworkError: falha de conectividade ou DNS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from tools.registry import ToolResult

log = logging.getLogger(__name__)


class ErrorTaxonomy:
    COMMAND_NOT_FOUND = "CommandNotFound"
    PERMISSION_DENIED = "PermissionDenied"
    WINDOW_NOT_FOUND = "WindowNotFound"
    TIMEOUT = "Timeout"
    INVALID_OUTPUT = "InvalidOutput"
    NETWORK_ERROR = "NetworkError"
    SCHEMA_VIOLATION = "SchemaViolation"
    RESOURCE_UNAVAILABLE = "ResourceUnavailable"
    VERIFICATION_FAILED = "VerificationFailed"
    INJECTION_SUSPECTED = "InjectionSuspected"


@dataclass
class Verdict:
    """Veredito booleano determinístico de pós-condições."""

    passed: bool
    check_name: str
    message: str = ""

    @classmethod
    def all(cls, *verdicts: Verdict) -> Verdict:
        for v in verdicts:
            if not v.passed:
                return v
        return Verdict(passed=True, check_name="all_checks", message="Todas as pós-condições foram verificadas.")


@dataclass
class VerificationResult:
    """Resultado da verificação do estado real após execução."""

    verified: bool
    action_type: str
    check_type: str
    details: str
    taxonomy_error: str | None = None
    suggested_recovery_route: str | None = None
    meta: dict = field(default_factory=dict)


class ActionVerifier:
    """Verificador empírico do impacto das ações do agente no Windows 11."""

    def verify(
        self,
        action_type: str,
        action_params: dict,
        tool_result: ToolResult,
    ) -> VerificationResult:
        """Checa o estado pós-execução e classifica qualquer discrepância."""
        # Se a ferramenta já retornou ok=False, categoriza o erro e sugere contorno
        if not tool_result.ok:
            return self._diagnose_failure(action_type, action_params, tool_result.error or "Erro não especificado.")

        # Se retornou ok=True, executa verificação de fato no sistema
        checker = getattr(self, f"_verify_{action_type}", self._verify_generic)
        return checker(action_params, tool_result)

    def _diagnose_failure(self, action_type: str, params: dict, error_msg: str) -> VerificationResult:
        low_err = error_msg.lower()

        if any(w in low_err for w in ("não encontrado", "not found", "não é reconhecido", "cannot find")):
            tax = ErrorTaxonomy.COMMAND_NOT_FOUND
            if action_type == "ui_action" and params.get("action") == "open_app":
                app_name = params.get("app", "")
                recovery = f"Buscar executável no Registro e Menu Iniciar, ou abrir versão web de '{app_name}' no navegador."
            else:
                recovery = "Verificar caminho absoluto ou buscar nome correspondente no sistema."
        elif any(w in low_err for w in ("permissão", "permission", "access denied", "negado")):
            tax = ErrorTaxonomy.PERMISSION_DENIED
            recovery = "Solicitar confirmação elevada ou operar em diretório dentro da sandbox permitida."
        elif any(w in low_err for w in ("timeout", "tempo limite", "timed out")):
            tax = ErrorTaxonomy.TIMEOUT
            recovery = "Repetir operação com timeout estendido ou verificar se processo travou."
        elif any(w in low_err for w in ("conexão", "connection", "dns", "rede", "url")):
            tax = ErrorTaxonomy.NETWORK_ERROR
            recovery = "Tentar endpoint alternativo ou usar dados em cache local."
        else:
            tax = ErrorTaxonomy.INVALID_OUTPUT
            recovery = "Reformular parâmetros da ação e tentar rota alternativa."

        return VerificationResult(
            verified=False,
            action_type=action_type,
            check_type="tool_error",
            details=f"Ferramenta falhou com: {error_msg}",
            taxonomy_error=tax,
            suggested_recovery_route=recovery,
        )

    def _verify_generic(self, params: dict, result: ToolResult) -> VerificationResult:
        out = (result.output or "").strip()
        if not out:
            return VerificationResult(
                verified=False,
                action_type="generic",
                check_type="output_empty",
                details="Ação retornou sucesso mas saída de texto estava vazia.",
                taxonomy_error=ErrorTaxonomy.INVALID_OUTPUT,
                suggested_recovery_route="Re-executar ação solicitando dados explícitos.",
            )
        return VerificationResult(
            verified=True,
            action_type="generic",
            check_type="non_empty_output",
            details="Ação concluiu com saída válida.",
        )

    def _verify_ui_action(self, params: dict, result: ToolResult) -> VerificationResult:
        sub_action = params.get("action", params.get("ui_action", ""))

        if sub_action in ("open_app", "launch"):
            app_target = str(params.get("app", params.get("name", ""))).lower()
            # Verifica se alguma janela contém o nome do app
            try:
                import pygetwindow as gw
                windows = gw.getAllTitles()
                matched = bool(app_target) and any(app_target in t.lower() for t in windows if t.strip())
                if matched:
                    return VerificationResult(
                        verified=True,
                        action_type="ui_action",
                        check_type="window_created",
                        details=f"Janela de '{app_target}' confirmada ativa no Windows.",
                    )
            except Exception:
                pass
            return VerificationResult(
                verified=False,
                action_type="ui_action",
                check_type="dispatch_only",
                details=f"Comando para '{app_target}' disparado, mas nenhuma janela correspondente foi confirmada.",
                taxonomy_error=ErrorTaxonomy.VERIFICATION_FAILED,
                suggested_recovery_route="Inspecione as janelas antes de repetir a abertura.",
            )

        if sub_action in ("screenshot", "screen_vision"):
            img_path = result.meta.get("path") or result.meta.get("image_path")
            if img_path and Path(img_path).exists() and Path(img_path).stat().st_size > 0:
                return VerificationResult(
                    verified=True,
                    action_type="ui_action",
                    check_type="file_exists",
                    details=f"Screenshot verificado em disco ({Path(img_path).stat().st_size} bytes).",
                )
            return VerificationResult(
                verified=False,
                action_type="ui_action",
                check_type="file_missing",
                details="Arquivo de screenshot não foi gravado ou está vazio.",
                taxonomy_error=ErrorTaxonomy.INVALID_OUTPUT,
                suggested_recovery_route="Repetir captura de tela via mss ou pyautogui.",
            )

        if sub_action in ("list_apps", "list_windows"):
            apps = result.meta.get("apps", [])
            return VerificationResult(
                verified=True,
                action_type="ui_action",
                check_type="list_populated",
                details=f"Listagem confirmada ({len(apps)} itens detectados).",
            )

        return self._verify_generic(params, result)

    def _verify_browser(self, params: dict, result: ToolResult) -> VerificationResult:
        action = str(params.get("action") or "").lower()
        if action in {"click", "type", "media_status"}:
            verified = result.meta.get("verified") is True
            return VerificationResult(verified, "browser", result.meta.get("check", "unknown"),
                "Pós-condição observada na página." if verified else
                "Entrada enviada; o efeito ainda precisa ser observado. Não repita a ação sem conferir o estado.",
                taxonomy_error=None if verified else ErrorTaxonomy.VERIFICATION_FAILED,
                suggested_recovery_route=None if verified else "Leia o estado da página e confira a pós-condição desejada.")
        return self._verify_generic(params, result)

    def _verify_write_file(self, params: dict, result: ToolResult) -> VerificationResult:
        from tools.file_tool import MAX_WRITE_BYTES

        path_str = params.get("path", "")
        content = params.get("content", "")
        details = "Não foi possível confirmar o conteúdo escrito."
        try:
            if not isinstance(path_str, str) or not path_str or not isinstance(content, str):
                raise ValueError("Caminho ou conteúdo inválido")
            expected = content.encode("utf-8")
            if len(expected) > MAX_WRITE_BYTES:
                raise ValueError("Conteúdo excede o limite de escrita")
            path = Path(path_str)
            if not path.is_absolute():
                resolved = result.meta.get("path")
                if not isinstance(resolved, str) or not Path(resolved).is_absolute():
                    raise ValueError("Ferramenta não informou caminho absoluto resolvido")
                path = Path(resolved)
            if not path.is_file():
                details = f"Arquivo '{path_str}' não foi encontrado após escrita."
            elif path.stat().st_size != len(expected):
                details = "O tamanho do arquivo difere do conteúdo solicitado."
            else:
                with path.open("rb") as stream:
                    matches = stream.read(len(expected) + 1) == expected
                if matches:
                    return VerificationResult(
                        verified=True, action_type="write_file", check_type="file_content_verified",
                        details=f"Arquivo '{path_str}' verificado em disco: conteúdo UTF-8 idêntico ({len(expected)} bytes).",
                    )
                details = "O conteúdo em disco difere do conteúdo solicitado."
        except (OSError, ValueError, UnicodeError) as exc:
            details = f"Não foi possível verificar a escrita: {type(exc).__name__}."
        return VerificationResult(
            verified=False, action_type="write_file", check_type="file_content_mismatch",
            details=details, taxonomy_error=ErrorTaxonomy.INVALID_OUTPUT,
            suggested_recovery_route="Confira o arquivo e os parâmetros antes de repetir a escrita.",
        )

    def _verify_web(self, params: dict, result: ToolResult) -> VerificationResult:
        out = result.output or ""
        if "nenhum resultado direto encontrado" in out.lower():
            return VerificationResult(
                verified=False,
                action_type="web",
                check_type="empty_search",
                details=out,
                taxonomy_error=ErrorTaxonomy.INVALID_OUTPUT,
                suggested_recovery_route="Sanitizar os termos de busca removendo colchetes ou tentar consulta simplificada.",
            )
        return VerificationResult(
            verified=True,
            action_type="web",
            check_type="search_results_obtained",
            details="Dados obtidos com sucesso na consulta web.",
        )

    def _verify_project_status(self, params: dict, result: ToolResult) -> VerificationResult:
        out = result.output or ""
        if "GPU" in out or "CPU" in out:
            return VerificationResult(
                verified=True,
                action_type="project_status",
                check_type="telemetry_confirmed",
                details="Telemetria de hardware colhida com sucesso.",
            )
        return self._verify_generic(params, result)


def proc_exists(name: str) -> Verdict:
    """Verifica se um processo com o nome especificado está em execução no Windows."""
    try:
        import psutil

        name_low = name.lower()
        for p in psutil.process_iter(["name"]):
            p_name = (p.info.get("name") or "").lower()
            if name_low in p_name:
                return Verdict(passed=True, check_name="proc_exists", message=f"Processo '{name}' ativo.")
        return Verdict(passed=False, check_name="proc_exists", message=f"Processo '{name}' não encontrado.")
    except Exception as exc:
        return Verdict(passed=False, check_name="proc_exists", message=f"Erro ao verificar processo: {exc}")


def proc_closed(name: str) -> Verdict:
    """Verifica se um processo foi devidamente encerrado."""
    res = proc_exists(name)
    if not res.passed:
        return Verdict(passed=True, check_name="proc_closed", message=f"Processo '{name}' encerrado com sucesso.")
    return Verdict(passed=False, check_name="proc_closed", message=f"Processo '{name}' ainda permanece ativo.")


def file_has_content(path: str | Path, expected_text: str | None = None) -> Verdict:
    """Verifica se arquivo existe, tamanho > 0 e se contém texto esperado."""
    p = Path(path).resolve()
    if not p.exists():
        return Verdict(passed=False, check_name="file_exists", message=f"Arquivo '{p}' não existe.")
    if p.stat().st_size == 0:
        return Verdict(passed=False, check_name="file_size", message=f"Arquivo '{p}' está vazio (0 bytes).")
    if expected_text:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            if expected_text not in content:
                return Verdict(
                    passed=False,
                    check_name="file_content",
                    message=f"Conteúdo esperado '{expected_text}' ausente no arquivo '{p}'.",
                )
        except Exception as exc:
            return Verdict(passed=False, check_name="file_read", message=f"Erro ao ler arquivo '{p}': {exc}")
    return Verdict(passed=True, check_name="file_verified", message=f"Arquivo '{p}' validado com sucesso.")


def window_exists(title_substr: str) -> Verdict:
    """Verifica se uma janela com o título especificado está visível."""
    try:
        import pygetwindow as gw

        q = title_substr.lower()
        matches = [w for w in gw.getAllWindows() if q in w.title.lower() and w.title.strip()]
        if matches:
            return Verdict(passed=True, check_name="window_exists", message=f"Janela '{matches[0].title}' visível.")
        return Verdict(passed=False, check_name="window_exists", message=f"Janela '{title_substr}' não encontrada.")
    except Exception as exc:
        return Verdict(passed=False, check_name="window_exists", message=f"Erro ao buscar janela: {exc}")

