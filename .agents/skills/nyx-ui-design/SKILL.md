---
name: nyx-ui-design
description: Redesenhar e implementar a interface da Nyx (shell "Nyx HUD", tokens, painel Agora, cartões de ação e confirmação, paleta de comandos) e validar visualmente com capturas, contraste e checagem de texto cortado. O pet/mascote é congelado.
---

# Interface "Nyx HUD — Midnight Signal"

Leia `references/layout-spec.md` (estrutura e comportamento) e `references/design-tokens.md` + `design-tokens.json` (única fonte de cor/tipografia/espaço). **O pet/mascote não muda** (`assets/oxynisx/`, `assets/sprites/`, `src/ui/sprite_renderer.py`, `src/ui/pet_routine.py`): só o entorno.

## Por que redesenhar (achados da versão atual, renderizada offscreen)
- Visual de "dashboard SaaS" genérico com acento violeta/lavanda que **não tem relação com a personagem** (cabelo azul-marinho, capuz vermelho, grampo dourado, olhos âmbar/azul-turquesa).
- A tela inicial é uma grade de 6 cartões-link; a conversa, que é o centro de uma companheira, fica escondida num item de menu.
- Três painéis fixos (biblioteca, central, companhia) ocupam tela o tempo todo; ícones são glifos unicode inconsistentes.
- Texto cortado no cartão "Modelo local" ("Modo de demonstração"); cartão morto "Tarefas: Indisponível".
- Nada mostra, em tempo real, **o que a Nyx está percebendo e fazendo** — justamente o que prova que ela "sabe o que está acontecendo".
- Confirmações como diálogos modais interrompem o fluxo; configurações são formulário de comboboxes.
- `src/ui/desktop.py` tem ~1.900 linhas num arquivo só.

## Como implementar
1. Criar `src/ui/hud/` (shell, rail, status_strip, chat_view, action_card, confirm_card, agora_panel, palette, onboarding, settings) e migrar de `desktop.py` por partes, **sem perder funções** (testes de regressão antes).
2. Gerar o QSS a partir de `design-tokens.json` (`src/ui/tokens.py`); nenhuma cor literal fora dos tokens.
3. Ficar em **PyQt6 Widgets** (RAM/CPU baixos com jogo aberto). Só avaliar QML se o processo ocioso ficar ≤ 180 MiB e < 1% CPU. Nada de Electron/web view.
4. Fontes (Inter + JetBrains Mono, licenças OFL) empacotadas em `assets/fonts/`; registrar com `QFontDatabase` também no preview offscreen.
5. Ícones: SVG (Lucide, ISC) renderizados e coloridos por token; sem glifos unicode.
6. Windows 11: manter moldura nativa, ativar modo escuro (`DWMWA_USE_IMMERSIVE_DARK_MODE`) e backdrop Mica (`DWMWA_SYSTEMBACKDROP_TYPE`) quando o build ≥ 22621, com fundo sólido de fallback.

## QA visual obrigatório (cada marco de UI)
- `python tools/preview_desktop.py` e capturas de **todas** as telas em Midnight e Daylight, 100/125/150% de escala (`QT_SCALE_FACTOR`), salvas em `docs/evidence/ui/`. **Abra e olhe cada PNG** (você consegue ver imagens) e descreva problemas antes de corrigir.
- `tools/check_ui.py`: (a) nenhum texto cortado (comparar `QFontMetrics` com a largura útil do widget para QLabel/QPushButton/QTabBar), (b) contraste ≥ 4,5:1 para texto e ≥ 3:1 para componentes, (c) ordem de Tab e `setAccessibleName` nos controles, (d) nenhum timer ativo quando a janela está oculta ou com "reduzir movimento".
- Medir RAM/CPU do processo da UI ocioso e primeiro paint; registrar em `docs/evidence/ui/perf.md`.
- Teste de fumaça de interação (com `QTest`): abrir paleta (Ctrl+K), enviar mensagem, aprovar/negar cartão de confirmação, parar tarefa (Esc Esc), alternar Modo Privado.
