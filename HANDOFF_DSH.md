# Handoff — DeepSeek Harness assumiu o projeto

**Assumido em:** 2026-10-21 21:56 (America/Sao_Paulo).
**Sessão anterior:** ChatGPT/Codex, encerrada pelo usuário antes deste handoff.
**Última atualização deste arquivo:** 2026-10-21 22:15.

## O que o DSH fez

### Rodada 1 — 21:56 a 22:09

1. Leu a conversa compartilhada (https://chatgpt.com/s/cx_6ad95f3ab2f48191a0ee6981a1aa07be) por extração de texto; o link é uma SPA e não entrega o conteúdo em HTML puro.
2. Localizou o projeto em `<PROJETO>` e leu `STATUS.md`; conferiu o estado em disco (revisão de voz de 21:44-21:45, build/instalação de 21:46, suíte verde).
3. Verificou a suíte antes de mexer: 337 aprovados, 1 ignorado.
4. Implementou **preferências de voz na interface**:
   - `src/audio/tts.py`: `VoiceSettings` (voz, velocidade, volume) com validação/limites, `normalize_voice`, `normalize_speed`, `normalize_volume`, `sapi_rate`, `PT_BR_VOICES` e `TextToSpeech.configure()`. Kokoro recebe voz/velocidade e o volume escala as amostras; SAPI5 recebe volume 0–100 e taxa −10..10.
   - `src/ui/desktop.py`: seletor de voz, sliders de velocidade (70–150%) e volume (0–100%) com leitura numérica, botão **Ouvir uma amostra** e persistência em `desktop.ini`.
   - `packaging/build.ps1`: o stderr do PyInstaller abortava o build por causa de `$ErrorActionPreference = "Stop"`; agora a saída é coletada.
5. Testes novos: `tests/test_voice_settings.py` (23 casos) + 1 de UI; `tests/test_tts_conversation.py` atualizado.
6. Validação: 370 aprovados, 1 ignorado, Ruff limpo, captura `build/previews/desktop-voice-settings.png`.
7. Recompilou e instalou (ZIP `e96409…ac10f`, exe `39b685…68e1c`).

### Rodada 2 — 22:09 a 22:15

8. Trocou o `core/broker.py` decorativo por um **registro de modelos residentes com descarga real**: handle com callback de descarga, `release()` que de fato libera, despejo por prioridade, `unload_failures` e leitura de VRAM pelo `resource_snapshot` compartilhado.
9. `runtime_budget.py`: `under_pressure`, `release_idle_residents` e `_free_then_snapshot`; pedidos Ollama e cargas GGUF tentam liberar modelos ociosos quando a RAM fica abaixo de 3 GiB ou a VRAM livre abaixo de 1,5 GiB (carência de 60 s, ignorada sob pressão crítica).
10. `audio/stt.py`: registra `whisper:<modelo>`, marca uso por transcrição, `close_model()`/`close()` e recarga automática.
11. Testes: 8 novos (7 do broker + 1 de integração do STT). Suíte final **378 aprovados, 1 ignorado**, Ruff limpo.
12. Verificação real: whisper small transcreveu o fixture em 5,92 s, foi descarregado por pressão (`released=["stt"]`, `_model=None`) e recarregou em 3,66 s.
13. Recompilou e instalou: ZIP `722344…48af`, exe `3cd57c…a142`; `core.broker` confirmado no PYZ e autoteste da instalação com exit 0.

### Rodada 3 — 22:15 a 22:35

14. Criou `src/ui/pet_routine.py`: planejador puro de ciclos ociosos (olhar a cada 16–30 s, sobressalto em 18% das vezes, sono após 4 min sem atividade), com relógio e RNG injetáveis.
15. Integrou ao `OverlayWindow`: timer de 1 s, olhar temporário de 2,6 s, `surprised` de 0,8 s, `sleep`, e despertar em qualquer atividade (clique, controles, fala, escuta, pensamento, erro). Não dorme durante tarefa ou arrasto.
16. 9 testes novos (7 do planejador + 2 de UI). Suíte final **387 aprovados, 1 ignorado**, Ruff limpo; capturas `build/previews/pet-sleep.png` e `pet-look.png`.
17. Recompilou e instalou: ZIP `f6bcd2…d74b`, exe `98c20e…2af8`; `ui.pet_routine` confirmado no PYZ e autoteste exit 0.

### Rodada 4 — 22:15 a 22:40 (meta ampliada pelo usuário)

18. O usuário ampliou a meta: quase-AGI nível Codex, todas as ferramentas funcionais (incluindo navegador e jogos), subagentes, e interface mais minimalista/animada — **sem mexer no pet**. A meta foi registrada no goal da sessão e a rota em `docs/ROADMAP.md`.
19. Interface: paleta de comandos `Ctrl+K` (`src/ui/command_palette.py`, ações + conversas recentes), trilho de 78 px `Ctrl+B` com persistência, toasts (`src/ui/toast.py`), layout responsivo (<1120 px recolhe a companhia) e estilos novos no tema. A busca de conversas passou para `Ctrl+F`.
20. Correções de layout encontradas por captura: título da barra esticava na vertical, botões se espalhavam no trilho e a paleta tinha altura fixa errada (agora calculada por componentes).
21. 5 testes novos de UI. Suíte: **392 aprovados, 1 ignorado**, Ruff limpo; capturas `desktop-palette.png` e `desktop-rail.png`.
22. Recompilou e instalou: ZIP `c4390c…3415`, exe `338c92…e9c5`, autoteste exit 0.

### Rodada 5 — 22:40 a 22:50 (navegador real)

23. Criou `src/tools/browser_tool.py`: sessão Edge/Chrome via Chrome DevTools Protocol (porta própria, perfil temporário, headless por padrão). Ações: open/navigate, read, click, type, wait, screenshot, status, close.
24. Segurança: só http(s); `file:`, `javascript:` e `data:` recusados; limites de seletor/texto; captura confinada às raízes permitidas. `ToolSpec` ganhou `sensitive_probe`/`is_sensitive_for` e o `agent_loop` usa esse veredicto — clique e digitação pedem confirmação, leitura não.
25. `browser` entrou em `VALID_ACTION_TYPES`, na gramática GBNF e no registry (sinônimos "navegador"/"navegar"); dependência `websocket-client` adicionada a `requirements-windows.txt` e ao spec do PyInstaller.
26. Verificação real: Edge headless abriu página local, leu, digitou "Darlan", clicou e releu "Clicado: Darlan" (captura `build/previews/browser-check.png`). 11 testes novos; suíte **403 aprovados, 1 ignorado**.
27. Novo `--browser-check`: o executável congelado executou o mesmo fluxo e saiu com código 0. O `close()` agora derruba a árvore de processos e limpa filhos órfãos pelo perfil temporário (nenhum msedge sobrou). Instalação atualizada: ZIP `8304a2…9e8d`, exe `3f59c1…baad`.

### Rodada 6 — 22:50 a 23:05 (equipe ampliada)

28. `core/agent_team.py`: até 4 tarefas por pedido, 3 em paralelo, 2 passos por agente. Papéis agora: pesquisa, **navegador**, arquivos, sistema e **codigo**; cada um declara ferramentas e ações permitidas.
29. Recusas auditadas: fora do escopo, ação proibida (clique/`file://`), ferramenta sensível, consulta repetida e tempo limite de 150 s com `timed_out`. Resultados trazem `steps` e `tools`.
30. 4 testes novos; suíte **407 aprovados, 1 ignorado**. O teste com modelo real foi adiado: só 3,4 GiB de RAM livre, orçamento recusou o Qwen3.5 4B.
31. Recompilou e instalou; `--browser-check` e `--self-check` do congelado exit 0. ZIP `af75cf…1f84`, exe `845053…7798`.

### Rodada 7 — 23:05 a 23:25 (ciclo de código)

32. Novo `src/tools/code_task_tool.py`: roda `pytest` na pasta do projeto, lê a falha, pede um plano JSON de edições ao modelo e repete até passar (2 tentativas por padrão, teto 3). Sem `apply`, apenas propõe; com `apply`, faz backup e reverte se continuar vermelho.
33. Limites: raízes permitidas, 5 arquivos, 200 KB, extensões de texto, caminhos relativos sem escape, timeout de 300 s; ferramenta sensível e destrutiva só quando `apply=true`.
34. Correção importante: dentro do executável congelado `sys.executable` é o `Nyx.exe`; o ciclo agora prefere a venv do projeto, depois `NYX_PYTHON`, depois o Python do PATH.
35. Verificação real: projeto temporário com `add` subtraindo começou com pytest exit 1; o ciclo aplicou a correção e a rodada seguinte passou (exit 0). Suíte: **419 aprovados, 1 ignorado**.
36. Recompilou e instalou; `--browser-check` e `--self-check` exit 0. ZIP `009ddf…421f`, exe `5c99b6…3ece`.

### Rodada 8 — 23:25 a 23:40 (animações de interface)

37. Barra lateral passou a animar a largura (245↔78 px, 220 ms) com timer próprio; a `QVariantAnimation` compartilhada travava quando dois testes de UI rodavam em sequência — troca registrada no código.
38. Indicador de digitação no feed ("Nyx está pensando" + três pontos pulsando em laço), criado/removido junto com o estado de processamento; estilos no tema.
39. 2 testes novos; suíte **421 aprovados, 1 ignorado**; captura `build/previews/desktop-typing.png`.
40. Recompilou e instalou: ZIP `13a15b…8c1d`, exe `05108b…6ff25`; `--browser-check` e `--self-check` exit 0.

### Rodada 9 — 10:27 a 10:52 (IA local, correção de timeout e aceleração GPU CUDA)

41. Diagnóstico do timeout: o Windows estava iniciando Ollama em AppData que não possuía bibliotecas CUDA, executando em 100% CPU e demorando 77+ segundos por inferência.
42. Sincronizadas as bibliotecas CUDA 12/13 para o Ollama em AppData e configurado `src/core/ollama_service.py` para priorizar a instalação com suporte a GPU em `E:\Ollama\ollama.exe`.
43. `src/core/runtime_budget.py`: corrigida a fórmula de `model_weight_budget_bytes` que reduzia o orçamento para 0 bytes quando a RAM livre estava entre 1.5 e 2.2 GiB apesar dos 11 GiB de VRAM na RTX 3060.
44. Aumentados os timeouts de `OllamaClient` para 120s e `INFERENCE_GATE.slot` para 90s (anteriormente limitado a 45s), suportando cold loads de modelos de 9B e gerações densas.
45. Adicionados `DeepSeek-R1:latest` e `qwen3.5:9b` ao inventário `MODEL_PREFERENCE` em `src/core/llm_client.py`.
46. Validação real em hardware: inferência na GPU (100% GPU) respondeu em ~1s a 3s; suíte **421 aprovados, 1 ignorado**, Ruff 100% limpo, e todos os 34 testes funcionais de `test_all_nyx.py` aprovados.

### Rodada 10 — 11:15 a 11:45 (Correção do Ollama, Navegador Avançado, Papel Patch e Ciclo de Código com Modelo Real)

47. **Correção do Ollama e inferência local**:
   - Diagnóstico da causa raiz: `OLLAMA_FLASH_ATTENTION=1` em `ollama_service.py` causava crash (`error: invalid argument: --no-mmap`) por incompatibilidade entre versões do Ollama e novos binários llama-server no Windows+CUDA. Removida a flag forçada, deixando o Ollama autogerenciar aceleração.
   - Timeout em telemetria: `ollama_models` em `runtime_budget.py` tinha timeout rígido de 2.0s que falhava durante inferências na GPU, provocando falso alarme de falta de memória. Timeout expandido para 5.0s com retry automático.
   - Validação real de inferência: Qwen 3.5 4B executado na RTX 3060 a ~80.9 tokens/segundo, gerando JSON estruturado validado pelo schema.
48. **Navegador avançado (`src/tools/browser_tool.py`)**:
   - Extração estruturada: `links` (extrai até 200 links com texto e URL absoluta resolvida) e `tables` (extrai cabeçalhos e linhas de tabelas HTML).
   - Suporte a SPA: `wait_text` aguarda conteúdo assíncrono renderizado no DOM com timeout configurável.
   - Rolagem: `scroll` suporta `down`, `up`, `top`, `bottom`, quantidade de pixels e `selector` específico para scrollIntoView.
   - Gerenciamento de abas: `tabs` (lista abas abertas), `new_tab`, `switch_tab` e `close_tab`.
   - Autoteste do navegador atualizado e executado via Edge real com 100% de sucesso.
49. **Equipe de microagentes com escrita supervisionada (`src/core/agent_team.py`)**:
   - Novo papel `"patch"`: analisa falhas de teste e formula propostas de correção via `code_task` e leitura de arquivos.
   - Bloqueio rígido de segurança: `_action_denial_reason` barra explicitamente `apply=True` em microagentes, garantindo que escritas no disco só ocorram sob supervisão direta do agente principal e do usuário.
   - Papel `"navegador"` atualizado para suportar extração estruturada de links, tabelas, espera de texto e rolagem.
50. **Ciclo de código com modelo real (`code_task_tool.py`, `llm_client.py`)**:
   - Suporte a schemas JSON especializados em `OllamaClient.generate` e `RecoveringLLM.generate` através do `CODE_TASK_SCHEMA`.
   - Verificação em hardware real: executado teste de ponta a ponta com o modelo `qwen3.5:4b` na GPU em repositório temporário com teste falhando (`test_maths.py`). O modelo identificou o erro, propôs a correção precisa (`return a * b`), aplicou ao arquivo em disco e os testes passaram na 2ª rodada (`Passed: True`, `Result ok: True`).
51. **Validação da suíte**: **431 testes aprovados, 1 ignorado**, Ruff 100% limpo, e todos os 34 módulos funcionais em `test_all_nyx.py` aprovados.

## Como retomar

```powershell
cd '<PROJETO>'
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m pytest -q
.\packaging\build.ps1 -Clean      # gera dist\Nyx e o ZIP portátil
.\dist\Nyx\install.ps1            # instala em %LOCALAPPDATA%\Programs\Nyx
```

## Pendências registradas no STATUS.md

1. **Jogos/tela**: captura contínua e macros de jogos/desktop.
2. **Release Windows + updater** entre duas versões.
3. **Interface**: animações de layout e transições; o pet está aprovado e não deve ser alterado.

## Regra de convivência

Se outra sessão (ChatGPT/Codex) voltar a editar este repositório, ela deve ler este arquivo antes de sobrescrever mudanças do DSH e registrar aqui o que fez, com horário.

## Codex — 31/10/2026, 19:08 (America/Sao_Paulo)

- Novo prompt lido; documentação obrigatória revisada antes de editar. Branch
  codex/nyx-core-reliability-phase1, base 8bc57b5. Nenhuma publicação desta branch.
- Reprodução real do breaker global e de descoberta/abertura: três chamadas por
  nome, 15 nomes. 3/15 verificados no baseline; 13/15 após correções (dois web).
- Corrigidos breaker por operação/alvo, cooldown/meio-aberto, aliases/candidatos,
  atalhos sem argumentos, UWP por identidade de processo, Discord versionado e
  espera de 20 s. Trace por tarefa e painel de saúde conectados; contratos ampliados.
- 845 testes aprovados, 27 pulados, zero falhas em 54,694 s; Ruff aprovado.
  Relatórios em build/diagnostic; evidências sanitizadas versionáveis em docs/evidence.
- Pet/overlay não alterados, CompanionStage AST idêntico. Fases 0/1 não concluídas.
  Recursos/modelo ainda bloqueiam ensaio; não reduzidas reservas nem trocado modelo.
  LPAC/MCP/updater/lab/Studio congelados para novas features conforme novo prompt.

### Continuação de 31/10/2026 — diagnóstico de recursos e sessão CDP

- Quatro commits locais salvaram baseline, breaker/traces/saúde, catálogo/identidade
  e evidências. RAM caiu abaixo de 1 GiB em nova sondagem; inferência não validada.
  Erro agora distingue inventário ausente de orçamento e informa medidas reais.
- Retirados somente do índice os dois JSONs de runtime; arquivos locais preservados.
  Não reescrito histórico público. Scanner completo ainda pendente.
- Cinco timeouts reais de navegador foram reproduzidos. CDP estava em outra aba
  about:blank porque started interpretava saída do lançador como sessão perdida.
  Sessão conectada agora não reinicia; falha do transporte não repete comandos.
  Onze testes reais passaram após a correção. Regressão final: 868 aprovados,
  27 pulados, zero falhas, 54,087 s; Ruff aprovado, saída 0. Observação R0
  conectada por allowlist estrita; entrada/abertura/clipboard continuam sensíveis.

## Retomada Codex — 31/10/2026, 20:59 (America/Sao_Paulo)

- Usuário liberou RAM. Qwen4 real completou nove ações/oito arquivos/soma396;
  Steam consultada e jogo observado escolhido. Novos perfis manuais persistentes
  carregados antes da admissão de modelo: Normal8K, Jogo4K, Foco16K, Conservador
  preservado por padrão. Não alterada preferência de modelo nem reiniciada a Nyx.
- Benchmarks reais por perfil/modelo, três chamadas. Encontrados erros reais
  de delegação contra pedido, arquivo extra e total484. Catálogo reduzido para
  leitura+cálculo; restrição explícita de delegação na guarda; conferência estreita
  de operandos/total/intervalo e até duas correções antes de encerrar com erro.
- Rodada final: 6/6 tarefas reais, três por modelo, nove ações e soma396.
  883 testes aprovados, 27 pulados, zero falhas, 59,237 s; Ruff limpo. LPAC pulado.
  Evidências completas e falhas preservadas em docs/evidence. Pet intacto.
- Benchmark agora usa adaptadores reais para todo catálogo; somente leituras dos
  oito fixtures e cálculo podem ser executados. Fixtures ficam em build, não docs.
- Fase2 ainda parcial: sem streaming/primeirotoken, voz, auto-perfil de jogo/OBS,
  KVq8 e teste de saúde de flash attention; gates amplos não concluídos.

### Fechamento da rodada — 21:04

Metadados canônicos preservam identidade de caminho e resultado de cálculo nos
novos checkpoints; legados têm limites. Um smoke com adaptadores reais passou
em 35,76 s. Outro, em paralelo à suíte, foi recusado por RAM livre de 1,70 GiB,
abaixo do piso de carga fria do Normal; não tratado como falha semântica nem sucesso.
Corrigido o código de saída do driver comparativo: falha registrada retorna 1.

## Continuação Codex — 31/10/2026, 21:41 (America/Sao_Paulo)

- Texto livre em fluxo Ollama para saudações inequívocas/identidade, usando
  admissão e perfil existentes, sem schema/ferramentas. Cartão parcial com
  PlainText e persistência somente ao final; pet/overlay/CompanionStage intactos.
- Comparação Qwen4 real aquecido: primeiro trecho 0,125–0,281 s, resposta completa
  0,359–0,656 s; JSON anterior 1,797–1,859 s. Janela Qt de produção isolada:
  cartão em 0,219 s, conclusão em 0,453 s. Não operada a Nyx pessoal.
- Achado real de identidade humana falsa: instruções compactadas, conferência
  estreita e retenção antes de exibir identidade, no máximo uma regeneração.
  Identidade final Qt real em 0,734 s. Artefato antigo tecnicamente passed=true
  está explicitamente marcado como falha semântica no relatório, sem ser apagado.
- Erro de contexto 1K e prompt acima de 1000 caracteres tratados por compactação,
  sem ampliar reservas ou afrouxar o teste. Fixture Qt aguarda workers/deletes.
- Regressão final: 906 aprovados, 27 pulados, zero falhas, 50,337 s, saída 0;
  Ruff limpo. Fonte build/diagnostic/conversation-final-regression.xml.
- Ensaio de arquivos chegou a sete leituras e parou por RAM0,86GiB, sem soma;
  repetição sequencial parou após uma leitura por RAM0,90GiB. Fluxo completo
  não requalificado após compactação mais recente. Evidências e limites no relatório
  docs/evidence/conversation_stream_2026-10-31.md. Fase2 continua parcial.

## Continuação Codex — 31/10/2026, 21:47 (America/Sao_Paulo)

- Repetidas recusas por RAM motivaram diagnóstico sob demanda em Modelo local.
  Abertura consulta recursos gerais; nomes/working sets somente após clique
  explícito, sem Presença contínua, sem auditoria de nomes, sem encerrar apps.
- Worker Qt real isolado consultou 317 processos em 391 ms e exibiu seis grupos
  em 500 ms. Limite inicial250ms foi parcial; limite final1s concluiu na amostra.
  Listas parciais são identificadas. RSS agrupado não é memória privada exclusiva.
- Corrigida impressão CLI cp1252; JSON em disco continua UTF-8. Não alterada a
  guarda de recursos ou pontuação do driver de arquivos. Sem novo modelo/dependência.
- 913 aprovados, 27 pulados, zero falhas, 52,136 s, saída0; Ruff limpo. Evidências
  docs/evidence/resource_diagnostic_2026-10-31.md. Pet/overlay intactos.

## Continuação Codex — 01/11/2026, 13:03 (America/Sao_Paulo)

- Pacote fornecido pelo usuário lido, AGENTS/skills/SPEC instalados somente em
  caminhos inexistentes. Branch nyx-2 preserva commits até5fc8ee5; plano/progresso
  novos refletem gates parciais e não reiniciam trabalho validado.
- Foreground visível e clipboard acessível por probe Win32, sem ler clipboard.
- Repositório público e branch nyx-backups confirmados. Usuário aprovou suspensão
  dos novos envios públicos. CloudBackup bloqueia antes de qualquer preparo/git;
  UI desabilita nuvem mas mantém timer local. INIs fonte/instalação true→false,
  demais preferências e metadados dos backups/chave iguais. Sem mover/apagar dados.
- Três snapshots Fernet reais descartáveis: envios negados, bytes locais/chaves
  intactos, sem pasta cloud-backup. Não tocado/reiniciado app pessoal ou build antiga;
  instâncias já carregadas têm limite documentado. Migração privada não autorizada.
- Baseline Shadow DOM0/3 foi commitado antes da correção; implementação fica
  em fila M3 enquanto o runner/verificador independente M0 é estruturado.
- Regressão da suspensão:915 aprovados,27 pulados,zero falhas,56,581s,saída0;
  Ruff limpo. Windows/browser reais habilitados,LPAC opt-in pulado.

## Continuação Codex — 01/11/2026, 14:27 (America/Sao_Paulo)

- Manifesto50, runner parcial com modelo/TaskRunner reais, verificador independente
  de resultado de arquivo/conversa, script run_live e marcadores Windows.
  Requisições3×,150linhas no relatório;141bloqueadas por setup ainda ausente.
- Processo interrompido em leitura e cauda de trace NUL preservada localmente;
  retomada explícita R0 mantém linhas prontas. WinError5 ao trocar JSON tratado
  por gravação atômica+até10tentativas, sem apagar resultado anterior.
- Checker numérico perdeu omissão de calculator no primeiro run: oito leituras,
  soma certa mas método explícito não cumprido. Original preservado com avaliação
  posterior; guarda nova exige ferramenta antes de entregar total.3/3 finais,
  9ações cada,396,correções1/2/1. Não confundir ledger com auditoria OS independente.
- Regressão927aprovados,27pulados,0falhas,48,889s,saída0;Ruff incl.bench limpo.
  Evidências bench_method_2026-11-01.md. Não tocados pet/overlay/instância pessoal.
- Caminhos pessoais de três docs substituídos por placeholders, sem mover arquivos.
  Próximo: fixture Qt de produção/aprovação R1 e verificador Win32 independente
  para Apps; higiene CI/scanner de segredos segue pendente. Marcos continuam parciais.

## Continuação Codex — 01/11/2026, 14:56 (America/Sao_Paulo)

- Novo harness atravessa composer da DesktopWindow, controlador/TaskRunner,
  PermissionDialog real clicado viaQTest e ferramenta de abertura. Assistida,
  modelo4Breal, perfilNormal, voz/estudos desligados só nas preferências temporárias.
  Guardas permitem somente listagens/abertura do app escolhido. Nenhuma instância
  pessoal da Nyx ou app pessoal encerrado. Pet/overlay/fontes preservados.
- Calc/Notepad/Paint9/9 e nova rodada integrada9/9, com uma confirmação/uma ação
  por tarefa. Verificador independente usaWin32/processo e título exato para
  hostUWP. Nada de títulos pessoais/modeltext nos JSONs públicos; só traces locais.
- Apps:3/15casos executáveis no runner,nove/45tentativas; gatefalse por cobertura
  e falta de reset entre rodadas. O manifesto todo tem6/50casos prontos,44pendentes.
- 929aprovados,27pulados,zero falhas,50,637s,saída0;Ruff incl.bench limpo.
  Evidências native_app_ui_2026-11-01.md. PróximoCI/segredos M0 e demais apps.
