# Handoff — DeepSeek Harness assumiu o projeto

**Assumido em:** 2026-10-21 21:56 (America/Sao_Paulo).
**Sessão anterior:** ChatGPT/Codex, encerrada pelo usuário antes deste handoff.
**Última atualização deste arquivo:** 2026-10-21 22:15.

## O que o DSH fez

### Rodada 1 — 21:56 a 22:09

1. Leu a conversa compartilhada (https://chatgpt.com/s/cx_6ad95f3ab2f48191a0ee6981a1aa07be) por extração de texto; o link é uma SPA e não entrega o conteúdo em HTML puro.
2. Localizou o projeto em `E:\projeto\Nova pasta` e leu `STATUS.md`; conferiu o estado em disco (revisão de voz de 21:44-21:45, build/instalação de 21:46, suíte verde).
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
cd 'E:\projeto\Nova pasta'
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
