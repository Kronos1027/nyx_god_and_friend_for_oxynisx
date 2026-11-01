# TAREFA — Nyx 2: companheira de desktop funcional, verificada e com interface nova

## Resultado que eu quero receber
No meu PC (Windows 11 · Ryzen 7 5700X · 16 GiB RAM · RTX 3060 12 GiB), eu falo ou escrevo em português informal e a Nyx **faz de verdade, com verificação**:
1. abre qualquer programa instalado ("abre o navegador", "abre o zap", "abre o Spotify") e confirma que a janela apareceu;
2. controla o navegador (visível, com login persistente), pesquisa na web e responde **com fontes**;
3. controla o desktop (janelas, teclado, rolagem, colar texto, mídia) por UIA, atalhos e visão como último recurso;
4. conversa sobre qualquer assunto com baixa latência, lembra de mim entre sessões e pode ser acionada por voz ("Ei Nyx");
5. **sabe o que está acontecendo no PC** (janela ativa, o que toca, jogo, tarefa atual) com meu consentimento, Modo Privado e Modo Live;
6. nunca diz "feito" sem ter observado o resultado, e quando falha me diz **o que tentou, o erro real e o próximo passo**;
7. tem uma interface **nova, minimalista, futurista e útil** ("Nyx HUD — Midnight Signal") — **o pet/mascote fica exatamente como está**.
Isso não é "AGI": é um agente companheiro persistente. Documente limites reais.

## O que você já tem no repositório
`AGENTS.md` (regras duráveis, leia primeiro), `.agents/skills/*` (procedimentos: verificação real, desktop, navegador, modelo/recursos, interface, presença/memória/voz), `docs/SPEC_CAPACIDADES.md` (diagnóstico P1–P12 com evidências no código e fases técnicas), `docs/REFERENCIAS.md` (repositórios e modelos de referência), `docs/PROGRESS.md` e `docs/DECISOES.md`.
Causa mais provável do "não consegui depois de 6 tentativas": circuit breaker que desliga `ui_action` inteiro após 3 falhas e nunca reabre; catálogo de apps que só lê App Paths com nome exato; verificação de janela por exe idêntico; contrato que expõe 10 de ~40 ações; modelo de 3–4B com contexto ≤ 4096 por causa de reservas de RAM/VRAM. **Isso veio de leitura estática: confirme ou refute em hardware real no M0.**

## Como executar (uma entrega contínua)
- Comece em **modo plano**: leia `AGENTS.md`, `STATUS.md`, `LIMITACOES.md`, `HANDOFF_DSH.md` e o SPEC; escreva `docs/PLANO_EXECUCAO.md` (marcos, riscos, como verificar cada um) e **siga em frente sem esperar resposta**. Só pare nos pontos de aprovação do `AGENTS.md` §10.
- Trabalhe na branch `nyx-2`, marcos em ordem, um commit por assunto. Após cada marco rode o **gate** (skill `nyx-windows-live-verify`), atualize `docs/PROGRESS.md` e siga. M3 e M4 podem andar em paralelo depois do M2 (subagentes/worktrees); o shell e os tokens do M7 podem começar depois do M1, ligando-se a dados reais.
- Seu sandbox pode não ter desktop interativo. Se não tiver, **não simule**: atualize `tools/run_live.ps1`, peça para eu rodar uma vez por marco e leia o JSON em `docs/evidence/`.

## Marcos e gates (todos medidos em Windows real, 3 execuções, verificador independente)
- **M0 Fundação e baseline.** Branch; higiene do repo público (`.gitignore` para `logs/*.json` e `logs/traces/`, `git rm --cached` nos logs versionados, sanitizar caminhos pessoais em `docs/`; **proponha** o que fazer com a branch `nyx-backups` — backup criptografado em repo público — e espere minha decisão); `bench/` + `tools/run_bench.py` + `tools/run_live.ps1` + `tools/diagnose_capabilities.py`; baseline em `docs/evidence/`; P1–P12 marcados CONFIRMADO/REFUTADO. *Gate:* baseline commitado.
- **M1 Destravar.** Breaker por (ferramenta, ação, alvo) com meio-aberto e reset por tarefa; só falha dura abre; catálogo composto (App Paths + Menu Iniciar + `Get-StartApps` + Steam) com aliases/fuzzy e `AMBIGUOUS` com candidatos; verificação multi-sinal (até 20 s, descendentes, UWP); contrato `ui_action` completo e compacto + macro-ações; erros tipados, escada de estratégias, encerramento honesto. *Gate:* Apps ≥ 95% · Desktop ≥ 90%.
- **M2 Cérebro e recursos.** Orçamento por VRAM; contexto 8–16K com KV q8_0; saída por orçamento; roteador conversa×agente; tool calling nativo + schema mínimo; poda de ferramentas e prefixo estável; perfis Normal/Jogo/Foco; benchmark de modelos (candidatos em `docs/REFERENCIAS.md`) e escolha por evidência. *Gate:* 1º token < 1,5 s · multi-etapa ≥ 80% · VRAM Normal ≤ 9,5 GiB · sem "preferred_model_deferred" com ≥ 8 GiB livres.
- **M3 Navegador e pesquisa.** Visível + perfil persistente; observação por árvore de acessibilidade com refs; frames/shadow DOM/abas/downloads/mídia; spike CDP×Playwright; pesquisa em camadas com fontes. *Gate:* Navegador ≥ 85% · Pesquisa ≥ 85%.
- **M4 Desktop robusto e habilidades por app.** UIA em processo auxiliar empacotável; visão/OCR sob demanda; habilidades Spotify/Discord/Steam/OBS/VS Code/Explorador/Configurações/Chrome-Edge; foco de janela confiável; DPI 100/125/150%. *Gate:* Desktop ≥ 90% · 10 apps validados.
- **M5 Confiança graduada.** Classes R0–R3 por código; aprovação por plano; modo Parceira persistente; allowlists; parada global. *Gate:* tarefa de 6 passos R0/R1 com ≤ 1 confirmação · nenhuma R3 sem confirmar nos testes adversariais.
- **M6 Presença, memória e voz.** Skill `nyx-presence-memory-voice`. *Gate:* Presença/memória ≥ 90% · Modo Privado/Live comprovados · wake→1ª palavra < 2,5 s.
- **M7 Interface Nyx HUD.** Skill `nyx-ui-design`: shell novo (rail, status strip, conversa, painel AGORA, cartões de ação/confirmação/pesquisa, paleta Ctrl+K, mini-HUD, onboarding), tokens da paleta do mascote, fontes e ícones empacotados, `desktop.py` desmembrado em `src/ui/hud/`. *Gate:* capturas de todas as telas (Midnight/Daylight, 100/125/150%) **olhadas e corrigidas**, `tools/check_ui.py` sem texto cortado e contraste OK, UI ociosa ≤ 180 MiB e < 1% CPU, smoke de interação com `QTest`.
- **M8 Aceitação final e entrega.** Bateria completa 3×; soak de 2 h; revisão de segurança (R3, injeção de prompt, Modo Privado); README/STATUS/LIMITACOES com números reais; relatório final no formato do `AGENTS.md` §11.

## Regras de teste (inegociáveis)
Aceitação é em Windows real com verificador independente (não o código da Nyx). Mocks só em testes unitários. Cada falha ganha trace e regressão. **Falso sucesso = 0**, senão o marco não fecha. Nunca afrouxe verificador, reduza execuções ou marque `verified` sem observar. Sempre registre o que **não** foi validado.

## Quando parar e me perguntar
Somente os pontos do `AGENTS.md` §10 (baixar > 5 GiB, instalar software de sistema, apagar meus dados, publicar/tornar público, mexer em backups/credenciais, reduzir proteção). Todo o resto: decida, registre em `docs/DECISOES.md` e continue.

## Definição de pronto da tarefa inteira
Os gates M0–M8 passaram; `docs/PROGRESS.md` mostra todos os marcos concluídos com evidência; a branch `nyx-2` está pronta para eu revisar e mesclar; o relatório final lista capacidades reais, limites reais e instruções de uso/retomada.
