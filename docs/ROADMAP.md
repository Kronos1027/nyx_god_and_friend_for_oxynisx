# Nyx — rota para uma quase-AGI (estado e prioridades)

Atualizado em 2026-10-21 pelo DeepSeek Harness. A meta declarada pelo usuário: chegar ao nível
de um agente como o Codex do ChatGPT — criar, pesquisar, programar, controlar o Windows, o
navegador e jogos, conversar e orquestrar subagentes menores — com tudo funcional e testado.
Isto é um mapa honesto do que existe, do que falta e da ordem sugerida; não é uma promessa.

## Matriz de capacidades

| Capacidade | Estado | Evidência / lacuna |
|---|---|---|
| Conversa local | Funciona | Ollama + Qwen3.5 4B, fila e orçamento de memória; qualidade depende do modelo |
| Criar arquivos e pastas | Funciona | `file_tool` com sandbox de raízes e verificação de escrita |
| Programar / executar código | Bom | `code_task` roda pytest, propõe/aplica correções com backup e reversão; `shell`/CodeAct seguem em allowlist |
| Pesquisar na web | Parcial | `web_tool` + fila de estudos; sem navegador real, só requisições e trechos |
| Controlar o Windows | Parcial | `ui_tool` (pywinauto/pyautogui), janelas, teclado, mouse, clipboard |
| Controlar navegador | Funciona (CDP) | `browser_tool`: abrir, ler, clicar, digitar, esperar, capturar; falta extração estruturada e abas múltiplas |
| Jogos | **Ausente** | Dependeria de leitura de tela + mouse/teclado; nada específico |
| Microagentes | Bom | `agent_team`: 4 tarefas, 3 em paralelo, 2 passos, papéis pesquisa/navegador/arquivos/sistema/código; falta escrita supervisionada e orquestração longa |
| Memória de longo prazo | Parcial | SQLite/FTS + notas de estudo; sem consolidação nem esquecimento |
| Voz | Funciona | Kokoro pt-BR, faster-whisper, preferências de voz |
| Automação agendada | Parcial | Agenda de lembretes (só notifica) e estudos ociosos |
| Empacotamento/updater | Parcial | PyInstaller + updater verificado; nenhuma release publicada |
| Interface | Bom e melhorando | Paleta, trilho animado, toasts, indicador de digitação e responsivo; faltam transições entre páginas mais ricas |

## Ordem sugerida

1. **Navegador avançado** — extração estruturada (links, tabelas), espera de SPA, abas e
   download; a base CDP já funciona (ver `STATUS.md`).
2. **Equipe de agentes com escrita supervisionada** — hoje os 4 agentes só leem e relatam;
   falta um papel que proponha patches, com confirmação e testes antes de aplicar.
3. **Ciclo de código com testes** — base pronta (`code_task`); falta validar com o modelo real
   em projetos maiores e cobrir falhas de importação e testes lentos.
4. **Jogos e tela** — captura contínua, detecção simples de estado e macros; risco alto, por
   isso vem depois de navegador e agentes.
5. **Release e atualização** — publicar uma versão real e exercitar o updater entre duas versões.
6. **Interface** — animações de layout (trilho, painéis), transições entre páginas, estados de
   carregamento e atalhos; sem tocar no pet, que está aprovado.

## Regras que não mudam

- Nada de executar ações destrutivas sem confirmação; o modo autônomo só nasce de toggle de UI.
- Toda capacidade nova entra com teste automatizado e, quando possível, verificação real.
- O que não foi testado fica declarado como não testado no `STATUS.md`.
# Evolution 2.0 — acompanhamento

- A: baseline e primeira correção de execução/rollback concluídos; evidências
  em `EVOLUTION_2_BASELINE.md`. Auditoria das demais áreas continua por fase.
- B: governador, prioridade, cancelamento de espera, reutilização de contexto
  residente e NVML implementados. Telemetria e tarefas reais verificadas.
  Medição de memória comprometida, integração integral STT/TTS/visão e painel
  configurável ainda pendentes; não considerar a fase inteira concluída.
- C: eventos internos e processos autorizados, iniciativa contextual e interesses
  implementados e testados. Painéis conectados; sem vigilância de tela.
  Sensores de janelas/pastas/navegador e ajuste de traços persistentes permanecem
  como trabalho de integração, sem declarar capacidade geral de percepção.
- D: CDP com entrada real, locators DOM, abas, perfil isolado autorizado,
  formulários e verificação de mídia implementados. Ensaios locais reais passam;
  Spotify autenticado adiado pelo usuário. UIA com identidade/snapshot, modalidade,
  foco, entrada e captura passou em fixture Windows real (Qt 1,0/1,5).
  Múltiplos monitores, escalas de sistema e aplicativos diversos ainda não validados.
- E: tarefas persistentes e microagentes com recuperação.
- F: skills/MCP/Creation Studio e execução isolada real.
- G: laboratório supervisionado e avaliações independentes.
- H: voz, painéis, animações e integração.
- I: regressão, benchmarks, sessão prolongada, empacotamento.
- J: relatório por requisito, limitações e preparação de integração (sem promover main).

