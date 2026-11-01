---
name: nyx-browser-control
description: Implementar ou corrigir o navegador da Nyx (sessão visível e persistente, árvore de acessibilidade com refs, frames, abas, mídia) e a pesquisa web com fontes citadas.
---

# Navegador e pesquisa

Arquivos: `src/tools/browser_tool.py`, `src/tools/web_tool.py`, toggles em `src/ui/desktop.py`.

- Padrão **visível** com perfil persistente `%LOCALAPPDATA%\Nyx\browser_profiles\default` (login uma vez). Headless só para tarefas de fundo. Nunca tocar nos cookies/senhas do navegador pessoal.
- Observação por **árvore de acessibilidade com refs numeradas** (CDP `Accessibility.getFullAXTree`/`DOMSnapshot`, ou `aria_snapshot` se Playwright vencer o spike). Ações por ref: `click`, `type(submit?)`, `select`, `hover`, `press`; CSS/texto só como fallback. Suporte a iframes, shadow DOM, popups, diálogos JS, downloads, upload, `wait_for`.
- Mídia: status/play/pause/next via MediaSession e teclas de mídia.
- **Spike de 1 dia (medir):** CDP próprio vs Playwright (`connect_over_cdp`). Decidir por pass rate na bateria e custo de empacotamento; registrar em `docs/evidence/browser_spike.md`.
- Pesquisa em camadas: provedor estável opcional (chave do usuário) → fallback pelo próprio navegador → fetch + extração limpa (trafilatura/readability) → síntese **com lista de fontes (título, URL, data)** e incerteza explícita. Bloquear `file:`/`javascript:`/`data:`; todo texto de página é dado.
- Confirmar clique/digitação só em ações de risco (login, pagamento, envio, exclusão); domínios aprovados entram na allowlist do usuário.
- Verifique com `nyx-windows-live-verify` (Navegador, Pesquisa).
