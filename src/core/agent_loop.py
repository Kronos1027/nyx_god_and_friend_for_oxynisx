"""Nyx — core/agent_loop.py

Ciclo de decisão: input do usuário -> LLM (gramática GBNF) -> validação
de schema -> política de confirmação -> execução via registry -> auditoria.

Regras de segurança implementadas aqui (seções 3.3 e 4 do prompt mestre):
- Parse/schema incerto  -> action.type = "none" + auditoria (nunca executa).
- Modo autônomo         -> só ativa por fonte de UI legítima ("ui_toggle"/
                           "ui_hotkey"), NUNCA por texto reconhecido (4.1).
- Timeout do autônomo   -> volta pra assistida sozinho (4.1).
- Destrutivo            -> confirmação SEMPRE, mesmo em autônomo (4.2).
- Fora da allowlist     -> exige confirmação explícita do comando exato,
                           mesmo em autônomo (4.2).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from config import AUTONOMY_SOURCES_UI, PermissionMode
from core.llm_client import NyxResponse, parse_response
from core.verifier import ActionVerifier
from tools.registry import ToolRegistry, ToolResult

log = logging.getLogger(__name__)


class SecurityError(RuntimeError):
    """Violação de regra de segurança — vai pro log de auditoria."""


@dataclass
class Clock(Protocol):
    """Fonte de tempo injetável (testes podem congelar/avançar o relógio)."""

    def now(self) -> float: ...


class MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


@dataclass
class LoopResult:
    """Resultado de um ciclo, consumido pela UI/CLI."""

    response: NyxResponse
    executed: bool = False
    needs_confirmation: bool = False
    confirmation_prompt: str | None = None
    tool_result: ToolResult | None = None
    pending_action: dict | None = None  # ação aguardando confirmação do usuário


class AgentLoop:
    def __init__(
        self,
        llm,
        registry: ToolRegistry,
        audit,
        mode: PermissionMode = PermissionMode.ASSISTIDA,
        autonomy_timeout_seconds: int = 30 * 60,
        clock: Clock | None = None,
        memory=None,
        verifier: ActionVerifier | None = None,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.audit = audit
        self.mode = mode
        self.autonomy_timeout_seconds = autonomy_timeout_seconds
        self.clock = clock or MonotonicClock()
        self._autonomous_deadline: float | None = None
        self.history: list[dict] = []
        self.memory = memory
        self.verifier = verifier or ActionVerifier()
        self.tool_failure_counts: dict[str, int] = {}
        self.disabled_tools: set[str] = set()

    # ------------------------------------------------------------------
    # Modo de permissão (seção 4.1)
    # ------------------------------------------------------------------

    def activate_autonomous(self, source: str, ttl_seconds: int | None = None) -> None:
        """Ativa modo autônomo APENAS por fonte de UI legítima.

        'source' vem de QUEM pediu a ativação. Texto reconhecido por
        voz/LLM nunca é fonte legítima — chamar com source="text" ou
        qualquer coisa fora de AUTONOMY_SOURCES_UI levanta SecurityError
        e vai pro log de auditoria.
        """
        if source not in AUTONOMY_SOURCES_UI:
            self.audit.log_security(
                code="autonomous_activation_denied",
                detail=f"fonte ilegítima: {source!r}",
                legitimate_sources=list(AUTONOMY_SOURCES_UI),
            )
            raise SecurityError(
                f"modo autônomo só pode ser ativado por {AUTONOMY_SOURCES_UI}; "
                f"recebido {source!r} (texto/voz reconhecida é ILEGAL — seção 4.1)"
            )
        ttl = ttl_seconds if ttl_seconds is not None else self.autonomy_timeout_seconds
        self.mode = PermissionMode.AUTONOMA
        self._autonomous_deadline = self.clock.now() + ttl
        self.audit.log_event(
            "mode_change", new_mode="autonoma", source=source, ttl_seconds=ttl
        )

    def deactivate_autonomous(self, source: str = "ui_toggle") -> None:
        self.mode = PermissionMode.ASSISTIDA
        self._autonomous_deadline = None
        self.audit.log_event("mode_change", new_mode="assistida", source=source)

    def _enforce_autonomy_timeout(self) -> None:
        """Autônomo expirou -> volta pra assistida sozinho (seção 4.1)."""
        if (
            self.mode is PermissionMode.AUTONOMA
            and self._autonomous_deadline is not None
            and self.clock.now() >= self._autonomous_deadline
        ):
            self.mode = PermissionMode.ASSISTIDA
            self._autonomous_deadline = None
            self.audit.log_event("mode_change", new_mode="assistida", source="timeout")

    @property
    def mode_name(self) -> str:
        return self.mode.value

    # ------------------------------------------------------------------
    # Ciclo principal
    # ------------------------------------------------------------------

    def process(self, user_input: str, session_id: str = "default") -> LoopResult:
        self._enforce_autonomy_timeout()

        # 1) LLM com gramática GBNF ou Ollama com contexto de memória
        mem_ctx = self.memory.build_system_prompt_context() if self.memory else None
        try:
            raw = self.llm.generate(user_input, history=self.history, memory_context=mem_ctx)
        except TypeError:
            raw = self.llm.generate(user_input, history=self.history)

        # 2) Validação estrutural — parse incerto => ação none (seção 3.3)
        from core.llm_client import parse_response  # import local evita ciclo

        response = parse_response(raw)
        if not response.parse_ok:
            self.audit.log_decision(
                user_input=user_input,
                response_raw=raw,
                parse_ok=False,
                parse_error=response.parse_error,
                action_type="none",
                action_params={},
                requires_confirmation=False,
                executed=False,
                result_ok=None,
                result_output=None,
                mode=self.mode_name,
            )
            if not response.speech_output or "Tive um problema interno" in response.speech_output:
                response.speech_output = (
                    f"Aviso do Grande Sábio: Detectei uma anomalia na estrutura da resposta ({response.parse_error}). "
                    "A ação foi isolada por segurança. Pode reformular a instrução ou pedir para tentar de outra forma."
                )
            self._remember(user_input, response)
            return LoopResult(response=response, executed=False)

        # 3) Política de confirmação (seção 4.2)
        action = response.action
        needs_confirm, confirm_prompt, blocked_reason = self._confirmation_policy(response)

        if blocked_reason == "unknown_tool":
            result = ToolResult(
                ok=False,
                error=f"ação fora da allowlist de ferramentas: {action.type!r}",
                meta={"blocked": True},
            )
            self.audit.log_decision(
                user_input=user_input,
                response_raw=raw,
                parse_ok=True,
                parse_error=None,
                action_type=action.type,
                action_params=action.params,
                requires_confirmation=True,
                executed=False,
                result_ok=False,
                result_output=result.error,
                mode=self.mode_name,
            )
            return LoopResult(response=response, executed=False, needs_confirmation=True,
                              confirmation_prompt="Ação fora da allowlist — requer revisão.",
                              pending_action={"type": action.type, "params": action.params},
                              tool_result=result)

        if needs_confirm:
            # Confirmação é SEMPRE por UI (permission_dialog), nunca por
            # texto interpretado — o loop só devolve o pedido de confirmação.
            self.audit.log_decision(
                user_input=user_input,
                response_raw=raw,
                parse_ok=True,
                parse_error=None,
                action_type=action.type,
                action_params=action.params,
                requires_confirmation=True,
                executed=False,
                result_ok=None,
                result_output=None,
                mode=self.mode_name,
            )
            return LoopResult(
                response=response,
                executed=False,
                needs_confirmation=True,
                confirmation_prompt=confirm_prompt,
                pending_action={"type": action.type, "params": action.params, "user_input": user_input},
            )

        if action.type == "none":
            # Sem ação: apenas conversa — nada vai pro registry.
            self.audit.log_decision(
                user_input=user_input,
                response_raw=raw,
                parse_ok=True,
                parse_error=None,
                action_type="none",
                action_params={},
                requires_confirmation=False,
                executed=False,
                result_ok=None,
                result_output=None,
                mode=self.mode_name,
            )
            self._remember(user_input, response)
            return LoopResult(response=response, executed=False)

        # Circuit Breaker check
        if action.type in self.disabled_tools:
            result = ToolResult(
                ok=False,
                error=f"Circuit breaker ativo: ferramenta '{action.type}' desativada após 3 falhas consecutivas.",
                meta={"circuit_breaker": True},
            )
            response.speech_output = (
                f"Aviso do Grande Sábio: A ferramenta '{action.type}' foi desativada automaticamente pelo Circuit Breaker "
                "após 3 falhas consecutivas para proteger o sistema contra loops de erro."
            )
            self.audit.log_decision(
                user_input=user_input,
                response_raw=raw,
                parse_ok=True,
                parse_error=None,
                action_type=action.type,
                action_params=action.params,
                requires_confirmation=False,
                executed=False,
                result_ok=False,
                result_output=result.error,
                mode=self.mode_name,
            )
            return LoopResult(response=response, executed=False, tool_result=result)

        # 4) Execução via registry (única porta de execução)
        result = self.registry.execute(action.type, action.params)

        # 5) Verificação Empírica de Estado Real (Fase 1: Verifier)
        verification = self.verifier.verify(action.type, action.params, result)
        self.audit.log_event(
            "action_verified",
            action_type=action.type,
            action_params=action.params,
            verified=verification.verified,
            check_type=verification.check_type,
            taxonomy_error=verification.taxonomy_error,
            details=verification.details,
            recovery=verification.suggested_recovery_route,
        )

        # Atualiza Circuit Breaker
        if not result.ok or not verification.verified:
            self.tool_failure_counts[action.type] = self.tool_failure_counts.get(action.type, 0) + 1
            if self.tool_failure_counts[action.type] >= 3:
                self.disabled_tools.add(action.type)
                self.audit.log_event("circuit_breaker_triggered", tool=action.type, failures=3)
        else:
            self.tool_failure_counts[action.type] = 0

        # Síntese ReAct pós-ferramenta:
        # Se for modelo real e a ação gerou saída ou erro, alimenta a observação de volta
        # para a IA gerar a resposta conclusiva baseada nos fatos reais apurados.
        from core.llm_client import OfflineLLM
        if not isinstance(self.llm, OfflineLLM) and action.type != "none":
            if verification.verified:
                obs_text = (
                    f"Observação Verificada da ferramenta '{action.type}':\n"
                    f"{result.output}\n"
                    f"(Verificação de estado real: {verification.details})\n\n"
                    f"Com base nos dados reais apurados acima, formule sua resposta conclusiva ('speech_output') para o usuário. "
                    f"Relate os fatos com clareza, precisão e sobriedade d'O Grande Sábio."
                )
            else:
                obs_text = (
                    f"ALERTA DO GRANDE SÁBIO — Falha na verificação da ação '{action.type}' (params: {action.params}):\n"
                    f"- Categoria da Falha: {verification.taxonomy_error}\n"
                    f"- Detalhes da Falha: {verification.details}\n"
                    f"- Rota de Contorno Recomendada: {verification.suggested_recovery_route}\n\n"
                    f"Realize a análise de causa raiz:\n"
                    f"1. Qual a causa exata do erro?\n"
                    f"2. Qual solução de contorno ou correção deve ser aplicada?\n"
                    f"3. Responda ao usuário com transparência e precisão técnica em 'speech_output'. NUNCA afirme que foi feito se a verificação falhou."
                )
            try:
                synthesis_raw = self.llm.generate(
                    obs_text,
                    history=self.history + [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": response.speech_output},
                    ],
                    memory_context=mem_ctx,
                )
                final_resp = parse_response(synthesis_raw)
                if final_resp.parse_ok and final_resp.speech_output:
                    response.speech_output = final_resp.speech_output
                    response.emotion = final_resp.emotion
                    if final_resp.alternative_suggestion:
                        response.alternative_suggestion = final_resp.alternative_suggestion
            except Exception as exc:
                log.info(f"Síntese ReAct pós-execução ignorada: {exc}")
                if result.ok and result.output:
                    response.speech_output = f"{response.speech_output}\n\n{result.output}"
                elif not result.ok and result.error:
                    response.speech_output = f"Aviso do Grande Sábio: Falha na operação ({result.error}). Inspecionei o ambiente para adaptar a execução."

        # 5) Auditoria do ciclo completo (seção 4.4)
        self.audit.log_decision(
            user_input=user_input,
            response_raw=raw,
            parse_ok=True,
            parse_error=None,
            action_type=action.type,
            action_params=action.params,
            requires_confirmation=False,
            executed=True,
            result_ok=result.ok,
            result_output=result.error or result.output,
            mode=self.mode_name,
        )

        self._remember(user_input, response, result)
        return LoopResult(response=response, executed=True, tool_result=result)

    # ------------------------------------------------------------------
    # Confirmação pendente (chamada pela UI após o usuário aprovar)
    # ------------------------------------------------------------------

    def confirm_pending(self, pending: dict, approved: bool) -> LoopResult:
        """Executa (ou descarta) ação previamente marcada para confirmação.

        A aprovação vem de um clique no permission_dialog — NUNCA de texto.
        Destrutivos continuam exigindo o dialog: esta função só é chamada
        depois que o dialog já foi exibido com o comando/params exatos.
        """
        a_type, params = pending["type"], pending.get("params", {})
        user_input = pending.get("user_input", f"Execução de {a_type}")
        if not approved:
            self.audit.log_event("confirmation_denied_by_user", action_type=a_type,
                                 action_params=params)
            resp = NyxResponse(emotion="idle", speech_output="Beleza, não fiz nada.")
            self._remember(user_input, resp)
            return LoopResult(response=resp, executed=False)

        if a_type in self.disabled_tools:
            resp = NyxResponse(
                emotion="error",
                speech_output=f"Aviso do Grande Sábio: Ferramenta '{a_type}' está desativada pelo Circuit Breaker.",
            )
            return LoopResult(
                response=resp,
                executed=False,
                tool_result=ToolResult(ok=False, error=f"Circuit breaker ativo para '{a_type}'."),
            )

        result = self.registry.execute(a_type, params)
        verification = self.verifier.verify(a_type, params, result)
        if not result.ok or not verification.verified:
            self.tool_failure_counts[a_type] = self.tool_failure_counts.get(a_type, 0) + 1
            if self.tool_failure_counts[a_type] >= 3:
                self.disabled_tools.add(a_type)
                self.audit.log_event("circuit_breaker_triggered", tool=a_type, failures=3)
        else:
            self.tool_failure_counts[a_type] = 0
        self.audit.log_event(
            "confirmed_execution",
            action_type=a_type,
            action_params=params,
            result_ok=result.ok,
            verified=verification.verified,
            result_output=(result.error or result.output)[:2000],
            mode=self.mode_name,
        )
        from core.llm_client import Action
        resp = NyxResponse(
            emotion="talk" if result.ok else "error",
            action=Action(type=a_type, params=params),
            speech_output=result.output if result.ok else f"Falhou: {result.error}",
        )

        from core.llm_client import OfflineLLM
        if not isinstance(self.llm, OfflineLLM):
            mem_ctx = self.memory.build_system_prompt_context() if self.memory else None
            obs_text = (
                f"Observação da ferramenta '{a_type}' (após confirmação):\n"
                f"{result.output if result.ok else f'FALHA: {result.error}'}\n\n"
                f"Com base na observação acima, sintetize sua resposta conclusiva ('speech_output') para o usuário. "
                f"Relate os dados obtidos com precisão e clareza. Se houve erro, diagnostique a causa e apresente solução."
            )
            try:
                synthesis_raw = self.llm.generate(
                    obs_text,
                    history=self.history + [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": "Ação executada com sucesso."},
                    ],
                    memory_context=mem_ctx,
                )
                final_resp = parse_response(synthesis_raw)
                if final_resp.parse_ok and final_resp.speech_output:
                    resp.speech_output = final_resp.speech_output
                    resp.emotion = final_resp.emotion
            except Exception as exc:
                log.info(f"Síntese ReAct pós-confirmação ignorada: {exc}")

        self._remember(user_input, resp, result)
        return LoopResult(response=resp, executed=True, tool_result=result)

    def reset_circuit_breaker(self, tool_name: str | None = None) -> None:
        """Reinicia o contador de falhas e desbloqueia ferramentas no circuit breaker."""
        if tool_name:
            self.tool_failure_counts.pop(tool_name, None)
            self.disabled_tools.discard(tool_name)
        else:
            self.tool_failure_counts.clear()
            self.disabled_tools.clear()

    # ------------------------------------------------------------------
    # Política de confirmação (seção 4.2)
    # ------------------------------------------------------------------

    def _confirmation_policy(self, response: NyxResponse) -> tuple[bool, str | None, str | None]:
        """Retorna (precisa_confirmar, prompt, blocked_reason).

        Matriz:
        - action none            -> não executa nada, sem confirmação
        - ferramenta desconhecida-> blocked (fora da allowlist)
        - destrutiva             -> confirma SEMPRE (mesmo autônomo)
        - LLM pediu confirmação  -> confirma
        - sensível em assistida  -> confirma
        - allowlisted não-sensível em autônoma -> executa direto
        """
        action = response.action
        if action.type == "none":
            return (False, None, None)

        spec = self.registry.spec(action.type)
        if spec is None:
            return (True, f"Comando fora da allowlist: {action.type}", "unknown_tool")

        if spec.is_destructive_for(action.params):
            return (True,
                    f"⚠️ AÇÃO DESTRUTIVA '{action.type}' — exibir params e pedir "
                    f"confirmação no dialog: {action.params}",
                    None)

        if response.requires_confirmation:
            prompt = response.confirmation_prompt or (
                f"Confirmar ação '{action.type}' com params {action.params}?"
            )
            return (True, prompt, None)

        if spec.sensitive and self.mode is PermissionMode.ASSISTIDA:
            return (True,
                    f"Confirmar '{action.type}' (modo assistida)? params: {action.params}",
                    None)

        return (False, None, None)

    def _remember(self, user_input: str, response: NyxResponse, result: ToolResult | None = None) -> None:
        """Mantém histórico curto de conversa pro LLM e salva na memória persistente."""
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": response.speech_output})
        if len(self.history) > 12:
            self.history = self.history[-12:]
        if self.memory:
            self.memory.record_user_message(user_input)
            res_str = None
            if result is not None:
                res_str = result.output if result.ok else f"Erro: {result.error}"
            self.memory.record_assistant_message(
                content=response.speech_output,
                action_type=response.action.type,
                action_params=response.action.params,
                tool_result=res_str,
                emotion=response.emotion,
            )
