"""Nyx — cli.py  (Fase 1)

Loop de decisão rodando via terminal, sem UI/voz — definition of done da
Fase 1: "log real de uma sessão de terminal rodando o loop via CLI".

Uso:
    python src/cli.py --offline          # modo offline (OfflineLLM, sem modelo)
    python src/cli.py --model models/qwen2.5-7b-instruct-q5_k_m.gguf
    python src/cli.py --session minha-sessao

O modo --offline usa um LLM determinístico de dev (OfflineLLM) que responde
ações seguras de demonstração. Ele NÃO é o modelo real — o comportamento do
Qwen2.5 com gramática GBNF só é validado na máquina Windows (STATUS.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from app_paths import activate_runtime

# Permite rodar `python src/cli.py` direto do repo.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Garante UTF-8 na saída padrão (Windows PowerShell usa cp1252 por padrão).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from audit.logger import AuditLogger  # noqa: E402
from config import NyxConfig, PermissionMode  # noqa: E402
from core.agent_loop import AgentLoop, SecurityError  # noqa: E402
from core.llm_client import OfflineLLM, create_llm_client  # noqa: E402
from core.memory import MemoryManager  # noqa: E402
from core.scheduler import ReminderScheduler  # noqa: E402
from tools.clipboard_tool import ClipboardTool, make_clipboard_tool_func  # noqa: E402
from tools.file_tool import FileTool, make_file_tool_func  # noqa: E402
from tools.macro_tool import MacroStore, make_macro_tool_func  # noqa: E402
from tools.project_watch_tool import ProjectWatchTool, make_project_watch_tool_func  # noqa: E402
from tools.registry import ToolRegistry, ToolSpec  # noqa: E402
from tools.shell_tool import ShellTool, make_shell_tool_func  # noqa: E402
from tools.ui_tool import UITool, make_ui_tool_func  # noqa: E402
from tools.workspace_tool import WorkspaceTool, make_workspace_tool_func  # noqa: E402
from tools.agent_team_tool import make_agent_team_tool_func, agent_team_contract  # noqa: E402

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def build_registry(cfg: NyxConfig) -> ToolRegistry:
    """Monta o registry com as ferramentas completas + specs de segurança."""
    cfg.ensure_dirs()
    registry = ToolRegistry()
    reminder_scheduler = ReminderScheduler(Path("data/nyx_schedule.db"))
    registry.reminder_scheduler = reminder_scheduler

    shell = ShellTool(dialect="powershell" if sys.platform == "win32" else "posix",
                      timeout=cfg.subprocess_timeout_seconds)
    registry.register(
        ToolSpec(name="shell", description="Comandos via allowlist de templates",
                 destructive=False, sensitive=True,
                 input_contract=shell.planner_contract(),
                 destructive_probe=lambda p: shell.is_destructive(p.get("template", ""))),
        make_shell_tool_func(shell),
    )

    ft = FileTool(cfg.allowed_roots)
    registry.register(
        ToolSpec(name="read_file", description="Lê arquivo (sandbox)",
                 destructive=False, sensitive=False),
        make_file_tool_func(ft, "read_file"),
    )
    registry.register(
        ToolSpec(name="write_file", description="Escreve arquivo (sandbox)",
                 destructive=False, sensitive=True),
        make_file_tool_func(ft, "write_file"),
    )
    registry.register(
        ToolSpec(name="find_files", description="Busca arquivos por glob (sandbox)",
                 destructive=False, sensitive=False),
        make_file_tool_func(ft, "find_files"),
    )
    registry.register(
        ToolSpec(name="delete_file", description="DESTRUTIVO: deleta arquivo (sandbox)",
                 destructive=True, sensitive=True),
        make_file_tool_func(ft, "delete_file"),
    )

    store = MacroStore(cfg.log_dir.parent / "macros")
    registry.register(
        ToolSpec(name="macro_run", description="Executa macro gravada",
                 destructive=False, sensitive=False),
        make_macro_tool_func(store, registry),
    )

    ui = UITool(screenshots_dir=cfg.log_dir.parent / "assets" / "screenshots", control=registry.control)
    registry.register(
        ToolSpec(
            name="ui_action",
            description="Automação desktop: janelas, screenshots, digitação e cliques",
            destructive=False,
            sensitive=True,
            destructive_probe=lambda p: ui.is_destructive(p.get("action", ""), p),
            input_contract={"action": "list_windows|focus_window|inspect_elements|read_element|click_element|type_element|screenshot|open_app",
                "hwnd": "Identificador retornado por list_windows; evita títulos ambíguos",
                "snapshot": "Obrigatório em read_element/click_element/type_element; retornado por inspect_elements, expira em 30 s",
                "id": "ID de controle da mesma inspeção", "text": "Texto para type_element",
                "verification": "click_element envia Invoke; depois leia o resultado com read_element/inspect_elements. Senhas exigem entrada humana."},
        ),
        make_ui_tool_func(ui),
    )

    clip = ClipboardTool()
    registry.register(
        ToolSpec(
            name="clipboard",
            description="Leitura, escrita e histórico da área de transferência",
            destructive=False,
            sensitive=False,
        ),
        make_clipboard_tool_func(clip),
    )

    pw = ProjectWatchTool(monitored_roots=cfg.allowed_roots)
    registry.register(
        ToolSpec(
            name="project_status",
            description="Monitoramento de hardware (CPU, RAM, GPU VRAM) e status Git",
            destructive=False,
            sensitive=False,
        ),
        make_project_watch_tool_func(pw),
    )

    ws = WorkspaceTool(control=registry.control)
    registry.register(
        ToolSpec(
            name="workspace",
            description="O Grande Sábio: exibe sub-janelas de código, planilhas, relatórios ou telemetria",
            destructive=False,
            sensitive=False,
        ),
        make_workspace_tool_func(ws),
    )

    from tools.web_tool import WebTool, make_web_tool_func

    web = WebTool()
    registry.register(
        ToolSpec(
            name="web",
            description="Pesquisa em tempo real na Web (DuckDuckGo/Wikipedia) e leitura de páginas",
            destructive=False,
            sensitive=False,
        ),
        make_web_tool_func(web),
    )

    from tools.browser_tool import BrowserSession, is_sensitive_action, make_browser_tool_func

    browser = BrowserSession(control=registry.control)
    ui.browser_session = browser
    registry.browser_session = browser
    import atexit

    atexit.register(browser.close)
    registry.register(
        ToolSpec(
            name="browser",
            description="Navegador real (Edge/Chrome) via CDP: abrir http(s), ler texto, clicar, digitar, esperar e capturar",
            destructive=False,
            sensitive=False,
            sensitive_probe=lambda p: is_sensitive_action(p.get("action")),
            input_contract={"action": "open|read|inspect|click|type|wait|wait_text|status|media_status|tabs|new_tab|switch_tab|close_tab|links|tables|screenshot|close",
                "url": "http(s), para open/new_tab", "selector": "CSS, para click/type/wait",
                "locator": "Alternativa a selector em click/type: {role, name}, {label} ou {text}; correspondência exata",
                "text": "Texto de type/wait_text", "expected_text": "Pós-condição de click; sem ela, clique enviado não prova conclusão",
                "tab_id": "ID retornado por tabs, para switch_tab/close_tab",
                "login": "inspect mostra indícios de login; peça interação humana. Nunca solicite senha no chat.",
                "playback": "media_status deve confirmar tempo de mídia avançando antes de dizer que está tocando; ausência de estado é incerteza."},
        ),
        make_browser_tool_func(browser, cfg.allowed_roots),
    )

    from tools.reminder_tool import make_reminder_tool_func
    registry.register(
        ToolSpec(name="schedule", description="Cria, lista e cancela lembretes locais", sensitive=False),
        make_reminder_tool_func(reminder_scheduler),
    )
    from core.evolution import EvolutionLab, make_evolution_tool_func
    registry.evolution_lab = EvolutionLab(Path("data/nyx_evolution.db"))
    from core.research import ResearchQueue
    registry.research_queue = ResearchQueue(registry.evolution_lab)
    registry.register(
        ToolSpec(name="evolution", description="Pesquisa persistente e simulação de habilidades propostas", sensitive=False),
        make_evolution_tool_func(registry.evolution_lab, registry),
    )
    return registry


def build_llm(args: argparse.Namespace, cfg: NyxConfig):
    if args.offline:
        print(f"{YELLOW}[modo offline — OfflineLLM determinístico, NÃO é o modelo real]{RESET}")
        demo_note = (
            "Nyx em modo offline: ciclo completo funcionando, mas sem Qwen2.5. "
        )
        sandbox = str(Path(cfg.allowed_roots[0].resolve() / "nota-demo.txt"))
        scripted = [
            json.dumps({
                "reasoning": "Pedido é uma listagem de diretório — LIST_DIR resolve.",
                "alternative_suggestion": None,
                "emotion": "talk",
                "action": {"type": "shell", "params": {"template": "LIST_DIR", "path": "."}},
                "requires_confirmation": False,
                "confirmation_prompt": None,
                "speech_output": "Listando o diretório atual...",
            }, ensure_ascii=False),
            json.dumps({
                "reasoning": "Guardar nota é escrita pequena dentro da sandbox.",
                "alternative_suggestion": None,
                "emotion": "talk",
                "action": {"type": "write_file",
                           "params": {"path": "nota-demo.txt", "content": "Nyx esteve aqui."}},
                "requires_confirmation": False,
                "confirmation_prompt": None,
                "speech_output": "Nota salva na sandbox.",
            }, ensure_ascii=False),
            json.dumps({
                "reasoning": "Deletar arquivo é destrutivo — uso o template "
                             "DELETE_FILE da allowlist e peço confirmação.",
                "alternative_suggestion": "Mover para uma pasta _trash na sandbox "
                                          "seria reversível.",
                "emotion": "surprised",
                "action": {"type": "shell",
                           "params": {"template": "DELETE_FILE",
                                      "path": sandbox}},
                "requires_confirmation": True,
                "confirmation_prompt": "Deletar nota-demo.txt? Isso não tem volta.",
                "speech_output": "Deletar o arquivo? Não dá pra desfazer.",
            }, ensure_ascii=False),
        ]
        llm = OfflineLLM(scripted=scripted)
        print(f"{DIM}{demo_note}3 respostas scripted disponíveis; depois cai no fallback.{RESET}")
        return llm

    if not (args.model and Path(args.model).is_file()):
        from core.ollama_service import ensure_local_ollama

        print(ensure_local_ollama().reason)
    llm, backend = create_llm_client(model_arg=args.model, offline=False, cfg=cfg)
    print(f"{CYAN}[cérebro da Nyx ativo via: {backend}]{RESET}")
    return llm


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nyx — loop via terminal (Fase 1)")
    ap.add_argument("--cli", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--offline", action="store_true",
                    help="roda com OfflineLLM (sem modelo GGUF/GPU)")
    ap.add_argument("--model", help="caminho do modelo GGUF")
    ap.add_argument("--session", default="cli", help="id da sessão (auditoria)")
    args = ap.parse_args(argv)

    activate_runtime()

    cfg = NyxConfig()
    cfg.log_dir = Path("logs")
    audit = AuditLogger(cfg.log_dir, session_id=args.session)
    registry = build_registry(cfg)
    llm = build_llm(args, cfg)
    registry.register(
        ToolSpec(name="agent_team", description="Delega até 4 investigações com dependências (3 independentes por vez, 2 passos cada), somente consultas permitidas", sensitive=False, input_contract=agent_team_contract()),
        make_agent_team_tool_func(llm, registry, audit),
    )
    from tools.code_task_tool import make_code_task_tool_func

    registry.register(
        ToolSpec(
            name="code_task",
            description="Roda a suíte de testes de um projeto e propõe ou aplica correções em rodadas, com backup e reversão",
            destructive=False,
            sensitive=True,
            destructive_probe=lambda p: bool(p.get("apply")),
        ),
        make_code_task_tool_func(llm, cfg.allowed_roots),
    )
    memory = MemoryManager(data_dir=Path("data"), session_id=args.session)
    loop = AgentLoop(llm, registry, audit, mode=PermissionMode.ASSISTIDA,
                     autonomy_timeout_seconds=cfg.autonomy_timeout_seconds,
                     memory=memory)

    print(f"{CYAN}════════ Nyx — agente desktop (Fase 1) ════════{RESET}")
    print(f"{DIM}modo: assistida (viseira verde) | sessão: {args.session}{RESET}")
    print(f"{DIM}comandos: sair | modo (mostra modo atual){RESET}")
    audit.log_event("session_start",
                    offline=args.offline, ts_local=datetime.now(timezone.utc).isoformat())

    pending: dict | None = None
    while True:
        try:
            user_input = input(f"{GREEN}você>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() == "sair":
            audit.log_event("session_end")
            break
        if user_input.lower() == "modo":
            print(f"{CYAN}modo atual: {loop.mode_name}{RESET}")
            continue

        if pending is not None:
            approved = user_input.lower() in ("s", "sim", "y", "yes")
            result = loop.confirm_pending(pending, approved)
            pending = None
            print(f"{CYAN}nyx>{RESET} {result.response.speech_output}")
            continue

        try:
            result = loop.process(user_input)
        except SecurityError as exc:
            print(f"{RED}[segurança]{RESET} {exc}")
            continue

        resp = result.response
        if not resp.parse_ok:
            print(f"{RED}[parse/schema falhou — ação bloqueada]{RESET} {resp.parse_error}")
        if resp.alternative_suggestion:
            print(f"{YELLOW}[sugestão melhor]{RESET} {resp.alternative_suggestion}")
        if result.needs_confirmation:
            print(f"{YELLOW}[confirmação necessária]{RESET} {result.confirmation_prompt}")
            print(f"{DIM}ação pendente: {result.pending_action}{RESET}")
            print(f"{DIM}responda 'sim' para aprovar ou qualquer outra coisa para negar{RESET}")
            pending = result.pending_action
            continue
        print(f"{CYAN}nyx>{RESET} {resp.speech_output}")
        if result.executed and result.tool_result:
            tr = result.tool_result
            status = f"{GREEN}ok{RESET}" if tr.ok else f"{RED}falhou: {tr.error}{RESET}"
            print(f"{DIM}[ação: {resp.action.type} → {status}]{RESET}")
            if tr.ok and tr.output:
                print(f"{DIM}{tr.output[:500]}{RESET}")

    print(f"{DIM}sessão encerrada — auditoria: {audit.path}{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
