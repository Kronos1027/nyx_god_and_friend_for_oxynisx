---
name: nyx-desktop-control
description: Implementar ou corrigir abertura de aplicativos, catálogo de apps, verificação de janela, UIA, atalhos, janelas e habilidades por app da Nyx no Windows 11.
---

# Controle de desktop confiável

Antes de editar leia `references/app-launch-ladder.md`. Arquivos centrais: `src/tools/installed_apps.py`, `src/tools/ui_tool.py`, `src/core/verifier.py`, `src/core/agent_loop.py` (circuit breaker), `src/cli.py` (contrato `ui_action`).

Regras:
- **Catálogo composto**: App Paths + Menu Iniciar (`.lnk`) + `Get-StartApps` (UWP/AUMID) + Steam + pastas comuns; aliases e busca aproximada; erro `AMBIGUOUS` devolve top-5 candidatos.
- **Lançamento sem shell livre**: `os.startfile(lnk)`; UWP via `explorer.exe shell:AppsFolder\<AUMID>` com AUMID validado por regex. Nunca interpolar entrada do usuário em comando.
- **Verificação por múltiplos sinais** até 20 s: janela nova por título/classe/pid, descendentes do processo lançado, `ApplicationFrameHost` com título do app, janela de processo criado após o disparo sob a pasta do app. App já aberto → focar e dizer isso.
- **Breaker por (ferramenta, ação, alvo)**, falha dura ≠ não verificado, meio-aberto com cooldown, reset ao iniciar nova tarefa.
- **Contrato completo e compacto** de `ui_action` (hotkey, scroll, colar texto, janelas, OCR/visão, mídia) + macro-ações (`open_and_focus`, `search_in_app`, `media`).
- Percepção em camadas: UIA → atalhos/APIs nativas → OCR/visão + coordenadas (último recurso, verificando por diff de tela). UIA em processo auxiliar (evita conflito COM/Qt).
- Habilidades por app em `skills/apps/` (Spotify, Discord, Steam, OBS, VS Code/Antigravity, Explorador, Configurações, Chrome/Edge): ações, risco, verificação, fallback. Jogos: só janela/processo/manifest; sem injeção.
- Teste cada mudança com `nyx-windows-live-verify` (categorias Apps e Desktop).
