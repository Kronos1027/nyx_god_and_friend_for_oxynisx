"""Nyx — main.py (Ponto de Entrada Unificado do Agente Desktop)

Permite executar tanto a interface desktop flutuante em PyQt6 quanto a interface CLI.

Uso:
    python src/main.py               # Inicia com Overlay PyQt6 e avatar pixel art
    python src/main.py --cli         # Inicia no modo terminal (CLI)
    python src/main.py --offline     # Inicia no modo offline (sem modelo pesado)
    python src/main.py --model path  # Especifica modelo GGUF
"""

from __future__ import annotations

import argparse
import logging
import json
import sys
import threading
from pathlib import Path

# Adiciona 'src' ao sys.path para imports limpos
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app_paths import activate_runtime
from app_version import __version__

from audit.logger import AuditLogger
from config import NyxConfig, PermissionMode
from core.agent_loop import AgentLoop
from cli import build_registry
from core.llm_client import create_llm_client
from core.memory import MemoryManager
from tools.registry import ToolSpec
from tools.agent_team_tool import make_agent_team_tool_func

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("nyx")


def build_llm_for_app(args: argparse.Namespace, cfg: NyxConfig):
    """Constrói o cliente LLM com fallback inteligente e seguro."""
    if not args.offline and not (args.model and Path(args.model).is_file()):
        from core.ollama_service import ensure_local_ollama

        service = ensure_local_ollama()
        log.info("Runtime local: %s", service.reason)
    client, backend = create_llm_client(model_arg=args.model, offline=args.offline, cfg=cfg)
    log.info(f"Cérebro da Nyx ativo via: {backend}")
    if not args.offline:
        from core.recovering_llm import RecoveringLLM

        def refresh():
            if not (args.model and Path(args.model).is_file()):
                from core.ollama_service import ensure_local_ollama
                ensure_local_ollama()
            refreshed, _ = create_llm_client(model_arg=args.model, cfg=cfg)
            return refreshed

        return RecoveringLLM(client, refresh)
    return client


def run_gui(args: argparse.Namespace) -> int:
    """Inicia a aplicação gráfica completa com Overlay PyQt6, áudio e hotkeys."""
    from PyQt6.QtWidgets import QApplication
    from audio.hotkey import HotkeyListener
    from audio.stt import SpeechToText
    from ui.overlay import OverlayWindow
    from ui.desktop import DesktopWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Nyx Desktop Agent")
    app.setApplicationVersion(__version__)

    cfg = NyxConfig()
    cfg.ensure_dirs()

    audit = AuditLogger(cfg.log_dir, session_id=args.session or "desktop")
    audit.log_event("session_start", mode="gui")

    registry = build_registry(cfg)
    llm = build_llm_for_app(args, cfg)
    registry.register(
        ToolSpec(name="agent_team", description="Delega até duas investigações paralelas somente de leitura", sensitive=False),
        make_agent_team_tool_func(llm, registry, audit),
    )
    memory = MemoryManager(data_dir=Path("data"), session_id=args.session or "desktop")

    loop = AgentLoop(
        llm=llm,
        registry=registry,
        audit=audit,
        mode=PermissionMode.ASSISTIDA,
        autonomy_timeout_seconds=cfg.autonomy_timeout_seconds,
        memory=memory,
    )

    from core.task_runner import TaskRunner
    loop.task_runner = TaskRunner(loop)
    overlay = OverlayWindow(loop=loop)
    desktop = None
    if getattr(args, "overlay", False):
        overlay.show()
    else:
        desktop = DesktopWindow(overlay)
        desktop.shutdown_requested.connect(app.quit)
        app.aboutToQuit.connect(desktop.close)
        desktop.show()

    # Inicializa STT e Hotkeys se não estiver em modo offline estrito
    stt = SpeechToText(model_name=cfg.whisper_model)
    listen_lock = threading.Lock()

    def on_listen_hotkey():
        if not listen_lock.acquire(blocking=False):
            overlay.voice_state_changed.emit("Já estou ouvindo. Termine a frase primeiro.", "listening")
            return

        def _worker():
            try:
                with overlay.tts.microphone_session():
                    overlay.voice_state_changed.emit("Ouvindo... Fale agora.", "listening")
                    text = stt.record_and_transcribe(duration_seconds=3.5)
                if text:
                    has_wake, prompt = stt.process_wake_word(text)
                    overlay.prompt_submitted.emit(prompt if has_wake else text)
                else:
                    overlay.voice_state_changed.emit("Nenhum áudio detectado.", "idle")
            except Exception as e:
                log.error(f"Erro no reconhecimento de voz: {e}")
                from core.runtime_budget import InferenceBusyError, InferencePressureError
                message = str(e) if isinstance(e, (InferenceBusyError, InferencePressureError, TimeoutError)) else "Falha ao capturar áudio. Confira o microfone e o modelo de voz."
                overlay.voice_state_changed.emit(message, "error")
            finally:
                listen_lock.release()

        threading.Thread(target=_worker, daemon=True).start()

    def on_autonomous_hotkey():
        overlay.mode_hotkey_requested.emit()

    def on_kill_switch_hotkey():
        overlay.screen_stop_requested.emit()

    hotkey_listener = HotkeyListener(
        on_listen=on_listen_hotkey,
        on_toggle_autonomous=on_autonomous_hotkey,
        on_kill_switch=on_kill_switch_hotkey,
    )
    hotkey_listener.start()

    overlay.voice_toggled.connect(on_listen_hotkey)

    # Mensagem de boas-vindas
    overlay.bubble.set_message("Estou por aqui. O que vamos fazer juntos?")

    try:
        ret = app.exec()
    finally:
        hotkey_listener.stop()
        audit.log_event("session_end")

    return ret


def main() -> int:
    parser = argparse.ArgumentParser(description="Nyx — Agente IA Desktop 100% Local (Windows 11)")
    parser.add_argument("--cli", action="store_true", help="Executa no terminal (modo CLI)")
    parser.add_argument("--offline", action="store_true", help="Usa o OfflineLLM sem carregar modelo GGUF")
    parser.add_argument("--overlay", action="store_true", help="Abre apenas o mascote compacto em vez da interface completa")
    parser.add_argument("--model", help="Caminho para o modelo GGUF")
    parser.add_argument("--session", default="main", help="ID da sessão para auditoria")
    parser.add_argument("--self-check", action="store_true", help="Verifica recursos, dependências e dados do aplicativo")
    args = parser.parse_args()

    activate_runtime()
    if args.self_check:
        from app_health import run_self_check

        report = run_self_check()
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] else 1

    if args.cli:
        import cli

        return cli.main()

    return run_gui(args)


if __name__ == "__main__":
    raise SystemExit(main())
