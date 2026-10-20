"""Nyx — config.py

Configuração central do agente: paths, budget de VRAM, allowlists e modos de
permissão. Toda constante de segurança nasce aqui (seção 4 do prompt mestre).

Padrão de modo inicial: ASSISTIDA (viseira verde) — o modo autônomo só é
ativado por toggle explícito de UI, nunca por texto reconhecido em runtime.
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from app_paths import is_frozen, resource_path


class PermissionMode(str, Enum):
    ASSISTIDA = "assistida"   # viseira verde — confirma ações sensíveis
    AUTONOMA = "autonoma"     # viseira âmbar — allowlist sem confirmação


# Fontes legítimas de ativação do modo autônomo. Qualquer coisa vinda de
# texto/voz reconhecida ("ativa o modo autônomo dito pelo usuário") é
# ILEGAL por definição — seção 4.1 do prompt mestre.
AUTONOMY_SOURCES_UI = ("ui_toggle", "ui_hotkey")

# Timeout do modo autônomo: volta pra assistida sozinho (seção 4.1).
AUTONOMY_TIMEOUT_SECONDS = 30 * 60  # 30 minutos


def _default_allowed_roots() -> list[Path]:
    """Diretórios onde o file_tool pode operar (seção 4.3).

    No Windows real: ~/Nyx e ~/Documents/Nyx.
    Em ambiente de dev/teste não-Windows: um diretório temporário isolado.
    """
    home = Path.home()
    if sys.platform == "win32":
        return [home / "Nyx", home / "Documents" / "Nyx"]
    dev_root = Path(tempfile.gettempdir()) / "nyx_dev_sandbox"
    dev_root.mkdir(parents=True, exist_ok=True)
    return [dev_root]


@dataclass
class NyxConfig:
    """Configuração única e explícita do agente."""

    # --- LLM local (seção 3.1) ---
    model_path: Path = Path("models/qwen2.5-7b-instruct-q5_k_m.gguf")
    n_gpu_layers: int = -1          # -1 = tudo na GPU (RTX 3060 12GB)
    n_ctx: int = 8192
    grammar_path: Path = field(default_factory=lambda: (
        resource_path("src/core/schema.gbnf") if is_frozen() else Path("src/core/schema.gbnf")
    ))
    vram_budget_gb: float = 11.5    # 12GB físicos com folga pro driver/monitor

    # --- Segurança (seção 4) ---
    mode: PermissionMode = PermissionMode.ASSISTIDA
    allowed_roots: list[Path] = field(default_factory=_default_allowed_roots)
    autonomy_timeout_seconds: int = AUTONOMY_TIMEOUT_SECONDS

    # --- Auditoria (seção 4.4) ---
    log_dir: Path = Path("logs")

    # --- STT (Fase 3) ---
    whisper_model: str = "small"    # tiny/small conforme budget de VRAM

    # --- Localização e Perfil do Usuário (Fase 1) ---
    user_city: str = ""
    user_profile_path: Path = Path("data/user_profile.json")

    # --- Modelo LLM Padrão Ativo ---
    active_llm_model: str = "qwen2.5:3b-instruct"

    # --- Execução e Orçamento de Passos ---
    subprocess_timeout_seconds: int = 20
    max_step_budget: int = 5

    def get_city(self) -> str:
        """Obtém a cidade configurada do usuário ou do perfil em disco."""
        if self.user_city:
            return self.user_city
        if self.user_profile_path.exists():
            try:
                import json
                data = json.loads(self.user_profile_path.read_text(encoding="utf-8"))
                if city := data.get("city"):
                    self.user_city = str(city).strip()
                    return self.user_city
            except Exception:
                pass
        return ""

    def save_city(self, city: str) -> None:
        """Salva a cidade no perfil persistente do usuário (perguntar uma única vez)."""
        self.user_city = city.strip()
        self.user_profile_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import json
            data = {}
            if self.user_profile_path.exists():
                try:
                    data = json.loads(self.user_profile_path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data["city"] = self.user_city
            self.user_profile_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao persistir cidade: {exc}")

    def ensure_dirs(self) -> None:
        """Cria diretórios necessários em runtime (idempotente)."""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def resolve_allowed_roots(self) -> list[Path]:
        """Raizes resolvidas (absolutas) para checagem de sandbox."""
        return [Path(r).expanduser().resolve() for r in self.allowed_roots]


def load_config(env: dict[str, str] | None = None) -> NyxConfig:
    """Carrega config com overrides por variável de ambiente (prefixo NYX_).

    NYX_MODEL_PATH, NYX_MODE (assistida|autonoma), NYX_WHISPER_MODEL,
    NYX_LOG_DIR, NYX_ALLOWED_ROOTS (separadas por os.pathsep).
    """
    env = env if env is not None else dict(os.environ)
    cfg = NyxConfig()

    if v := env.get("NYX_MODEL_PATH"):
        cfg.model_path = Path(v)
    if v := env.get("NYX_GRAMMAR_PATH"):
        cfg.grammar_path = Path(v)
    if v := env.get("NYX_WHISPER_MODEL"):
        cfg.whisper_model = v
    if v := env.get("NYX_LOG_DIR"):
        cfg.log_dir = Path(v)
    if v := env.get("NYX_ALLOWED_ROOTS"):
        cfg.allowed_roots = [Path(p) for p in v.split(os.pathsep) if p]
    if v := env.get("NYX_MODE"):
        try:
            cfg.mode = PermissionMode(v.lower())
        except ValueError as exc:
            raise ValueError(
                f"NYX_MODE inválida: {v!r} (use 'assistida' ou 'autonoma')"
            ) from exc

    # Segurança: config NUNCA inicia em autônoma a partir de variável de
    # ambiente — modo autônomo nasce só de toggle de UI em runtime.
    if cfg.mode is PermissionMode.AUTONOMA:
        cfg.mode = PermissionMode.ASSISTIDA

    return cfg
