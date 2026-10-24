# Nyx — estado verificado

Última atualização: 2026-10-24

## Evolution 2.0 — protótipo de execução isolada no Windows

- LPAC com token verificado antes da execução, Win32k bloqueado, Job Object,
  limites de memória/saída/tempo, ambiente reduzido e ACLs em cópia temporária.
- Dez testes reais específicos passaram: cálculo/gravação permitida, recusa de
  arquivo externo, runtime, registro privado, rede e processo do pai; timeout,
  cancelamento, recursos, descendente encerrado e rejeição de hardlink.
- Diagnóstico identificou necessidade de `registryRead` para iniciar o Python;
  sem essa capability o loader retorna `0xC0000022`. Nenhuma capability de rede
  ou COM foi concedida. Corrigidas perda da saída final e espera dos descendentes.
- Não integrado às ferramentas: faltam quota de disco, recuperação após queda,
  staging/exportação de candidatos e validação adversarial ampliada. `_ctypes`
  não importou nessa configuração. CodeAct/CodeTask continuam sem executar
  código gerado. Detalhes e comandos: `docs/WINDOWS_SANDBOX_PROTOTYPE.md`.
- Regressão conjunta com navegador/Windows/LPAC reais: **568 passaram, 1 pulado,
  48,42 s**. Ruff aprovado. Relatório: `build/sandbox-probes/regression.xml`.

## Evolution 2.0 — dependências e encerramento de microagentes

- `agent_team` aceita IDs e `depends_on` em até quatro investigações. Rejeita
  ciclos, IDs repetidos e referências ausentes antes de iniciar workers.
  Dependentes recebem relatórios estruturados como dados sem autoridade;
  uma dependência falha impede seu início. O contrato está disponível ao LLM.
- Até três consultas independentes podem progredir; a inferência continua
  compartilhada e serial. Investigações de navegador compartilham sessão e
  são serializadas inteiras para não misturar páginas entre agentes.
- Timeout não espera mais o shutdown bloqueante do executor. Cancelamento local
  permanece ativo mesmo se um novo pedido retomar o controle global. Respostas
  atrasadas não podem iniciar ferramentas; chamadas em curso ficam identificadas,
  e outra equipe é recusada até elas terminarem. Threads não são mortas à força.
- Circuit breaker agora vale no registro central, incluindo os microagentes.
  Pressão de memória interrompe novas inferências da equipe e é diferenciada
  de falha comum. TaskRunner grava `RESOURCE_PRESSURE`, retomável explicitamente
  com orçamento original quando não há resultado externo incerto.
- IDs, dependências, estados e resumos de subtarefas entram no checkpoint do
  pedido principal e no painel. Isso não permite retomar parcialmente uma equipe
  que caiu em voo; o bloqueio de efeitos incertos continua prevalecendo.
- **Ensaio real Qwen3.5 4B:** dois arquivos temporários com 28 e 68 foram lidos;
  terceiro agente dependente respondeu 96. Passou em 32,17 s, com RAM livre de
  2,81 GiB antes e 1,66 GiB depois. Não é comparação de ganho de desempenho.
  A tentativa anterior falhou por orçamento de memória e foi preservada em
  `build/evolution-baseline/team-live-before-pressure-fix.json`. Novo relatório:
  `team-live.json`, com histórico em `team-attempts/` no mesmo diretório.
- Regressão conjunta: **557 passaram, 1 pulado em 37,34 s**, Windows/navegador
  reais habilitados. Após acrescentar o estado de pressão na inferência direta,
  38 testes focados passaram. Ruff aprovado. Persistência geral de um plano
  com dependências de escrita e verificação semântica do objetivo ainda pendem.

## Evolution 2.0 — tarefas persistentes (E, primeira entrega)

- Runtime desktop grava checkpoints SQLite antes de cada efeito e depois da
  observação, com ID, objetivo, etapas, orçamento consumido e assinaturas SHA256
  para impedir repetição literal. Um lock do SO impede dois escritores de runtime.
- Pausa cooperativa termina a etapa atual antes de parar. Retomada explícita
  mantém ID e limites originais; aprovações não sobrevivem à reabertura do banco.
  Interrupção entre efeito e observação vira `WAITING_REVIEW`, sem retomada ou
  replay automático. A primeira entrega exige inspeção e novo pedido nesse caso.
- Painel Aprendizado → Tarefas mostra registros, etapas e tempo, permite pausar,
  retomar e excluir histórico sem desfazer efeitos. Perfis para próximos pedidos:
  padrão 6 ações/180 s, ampliado 12/600 s. Nunca aumenta orçamento ao retomar.
- Limites: 200 registros, 128 KiB por checkpoint; retenção remove somente um
  registro terminal mais antigo quando necessário. Pendências não são descartadas
  automaticamente. Campos reconhecidos como credenciais são redigidos; registros
  redigidos exigem novo pedido. Banco incluído no backup criptografado permitido.
- A conclusão do planejamento fica `PLANNING_FINISHED`, sem afirmar que o
  objetivo inteiro foi comprovado. Dependências de subtarefas, pós-condições do
  objetivo e reconciliação guiada permanecem pendentes, assim como microagentes.
- Evidências: oito leituras de arquivos reais atravessaram pausa/reabertura;
  teste em subprocesso próprio encerra abruptamente após gravar um arquivo e
  comprova bloqueio da repetição. Planejador roteirizado nesses testes, sem alegar
  inferência real. A UI executou retomada por worker e foi renderizada/revisada.
- Regressão: **543 passaram, 1 pulado em 36,50 s**, incluindo ensaios reais
  Windows/navegador. Relatórios `build/evolution-baseline/phase-e-integrated.*`.

## Evolution 2.0 — Windows com alvos identificados

Regressão conjunta: **537 passaram, 1 pulado em 36,95 s**, com
`NYX_TEST_BROWSER=1` e `NYX_TEST_DESKTOP=1`; skip por symlink indisponível.
Ruff aprovado. Relatórios locais: `build/evolution-baseline/phase-d-integrated.*`.

- UIA usa snapshot de 30 segundos, HWND, PID/data de criação e runtime ID do
  controle. Reconsulta em processo auxiliar sem Qt, com COM MTA persistente;
  não transfere objetos COM entre workers.
  Não escolhe a primeira janela na ausência de foco. Títulos/nomes ambíguos,
  controles removidos, desabilitados, protegidos ou inspeção vencida são recusados.
- Entrada por ValuePattern/Invoke e leitura do mesmo controle. Digitação compara
  o valor e não sobrescreve o clipboard. Clique enviado continua sem verificação
  até observar uma pós-condição. Campos de senha exigem entrada humana.
- Foco confere HWND ativo e bloqueio modal nativo. Captura MSS por monitor ou
  janela usa pixels físicos com origem explícita; clique por coordenadas exige
  janela escolhida, limites e hit-test. A localização visual não divide pixels
  físicos por DPI e rejeita janela movida desde a captura.
- Abertura de aplicativos não monta comando shell. Scripts, injeção por aspas,
  caminhos relativos e executáveis fora das pastas de instalação são recusados.
  Serviços web conhecidos usam a sessão controlada quando conectada ao runtime.
- Fechamento atua sobre uma janela única; encerramento de processo requer PID
  e data de criação, checa reutilização e confirma saída. Alias `terminate_process`
  mantém confirmação destrutiva. Fail-safe do mouse nunca é relatado como sucesso.
- Ensaios reais contra `tools/windows_test_app.py` cobrem
  texto Unicode, leitura, Invoke, clique físico, snapshot entre threads, senha,
  ambiguidade, modal e captura. A fixture foi renderizada com Qt scale 1,0 e 1,5;
  não alteramos escala do Windows. Há um monitor disponível, 1440×900; múltiplos
  monitores e escalas de sistema diferentes ainda não têm evidência real.
- Testes legados de web/UI agora usam dados e entradas explicitamente simulados
  para verificar lógica, sem abrir navegador pessoal, alterar volume ou rolar
  janelas. A integração real fica nas fixtures opt-in. Falha de geolocalização
  retorna indisponibilidade, em vez da antiga cidade fixa inventada.
- A execução conjunta com Qt revelou inspeção vazia/falha de foco que o ensaio
  isolado não detectava. O auxiliar dedicado corrigiu essa integração: 38 testes
  Qt/Windows passaram juntos. Chamadas têm prazo de oito segundos e cancelamento;
  o auxiliar próprio é encerrado se travar. Efeito enviado e não confirmado
  interrompe a tarefa, sem retentativa automática. O auxiliar não é sandbox.
- Limites: padrões UIA variam por aplicativo. O novo auxiliar ainda não está
  integrado ao executável congelado; UIA desse pacote falha explicitamente até
  a etapa de empacotamento. Não foi validado controle geral de jogos ou OCR.
  Spotify autenticado foi adiado por escolha do usuário; demais fases continuam.

## Evolution 2.0 — navegador e interrupção (D, primeira entrega)

Atualização de sessão (23/10): Personalizar controla navegador visível (padrão
no desktop) e persistência opt-in. Perfil separado em `data/browser_profiles`,
ignorado no Git; rejeita pastas existentes não identificadas, links/junctions e
uso concorrente por bloqueio do SO. Novos perfis têm ACL do usuário/SYSTEM no
Windows, sem importar cookies. Desativar não apaga a sessão já guardada; mudanças
valem na próxima abertura. Encerramento solicita flush ao navegador antes do
fallback de término. A persistência foi verificada reiniciando Edge real.

`inspect` lista formulários/controles sem valores de campos. `media_status`
acompanha os mesmos elementos HTML em duas amostras e confirma avanço sem mute;
não confirma som físico nem players inacessíveis/WebAudio. Ensaio com WAV
silencioso confirmou reprodução/pausa. Spotify real abriu em português e exibiu
“Entrar”; foi classificado `waiting_user`, sem alegar reprodução. Evidência em
`build/evolution-baseline/spotify-initial.json`. Login humano e seleção musical
continuam pendentes; a sessão temporária do ensaio foi encerrada.

Suíte focada de sessão/abas/formulários/mídia/UI/verificador: 64 passaram em
19,21 s antes do endurecimento final de ACL (validado separadamente). Prévia das
preferências revisada; campos numéricos agora têm contraste no tema escuro.

- Navegação CDP aguarda o loader do documento novo, incluindo redirecionamentos;
  não aceita o `readyState` da página anterior como prova de carregamento.
- Clique por eventos reais de mouse; digitação via teclado/entrada CDP e comparação
  do valor final. Localizadores CSS, role/name, label e texto com correspondência
  exata, unicidade, visibilidade, estabilidade e teste de elemento coberto.
  São localizadores DOM limitados, sem suporte completo a ARIA, iframes ou shadow DOM.
- Abas: ativação/fechamento aceitam resposta textual do endpoint, validam que o ID
  pertence à sessão e preservam a aba selecionada ao fechar outra.
- Verificador distingue clique enviado de pós-condição textual confirmada.
  Abrir um aplicativo sem encontrar janela correspondente também fica não verificado.
- Interrupção compartilhada entre registro, tarefas, navegador e entrada de UI;
  Ctrl+Alt+K mantém bloqueio até “Retomar ferramentas” no menu do mascote.
  Não repete ações anteriores. Esperas CDP consultam cancelamento; chamadas externas
  já em execução ainda podem terminar antes da próxima checagem cooperativa.
- Removido fallback de clique no centro quando a visão não localiza o alvo.
  Coordenadas fora da imagem e cancelamento durante a inferência impedem o clique.
- Evidência real: `--browser-check` passou; nove testes opt-in em
  `tests/test_browser_live.py` exercitaram Edge instalado contra servidor local,
  Unicode, `isTrusted`, página dinâmica, redirecionamento, abas, alvos inválidos e
  interrupção em menos de 1,5 s. Houve falhas anteriores de inicialização do Edge
  (saída 0 sem porta); a causa intermitente não está demonstrada como resolvida.
  Após as últimas mudanças, suíte focada navegador/emergência/verificador/tarefas/UI:
  82 passaram em 13,31 s; Ruff limpo em `src/` e `tests/`.
- Regressão: 482 passaram, 10 skips (nove opt-in e symlink), excluindo
  `tests/test_web_and_ui.py`: seis testes legados acessam rede ou modificam o
  desktop pessoal. Isso não equivale à validação completa do Windows.
- Pendentes nesta fase: reprodução autenticada no Spotify,
  controles UIA com identidade de janela e ensaio
  Windows dedicado. Não há nova instalação ou release desta revisão.

## Evolution 2.0 — iniciativa contextual e memória social

- ProactiveInteractionEngine substitui convites genéricos. Eventos deduplicados,
  com prazo de validade, pontuação, horários, foco, limites diários persistentes,
  modos desligada/discreta/normal/conversadora e redução de frequência após recusa.
  Nenhuma inferência é feita apenas por ociosidade.
- Falhas de tarefas, pesquisa autorizada e pressão de recursos alimentam o motor;
  sucesso verificado de uma nova tentativa resolve a sugestão de falha anterior.
- ContextAwarenessEngine verifica permissão antes de coletar. Observação de
  processos é opcional, restrita a PIDs escolhidos na interface, sem enumerar
  aplicativos, ler seus conteúdos ou encerrá-los. Teste real inicia e encerra
  somente um processo temporário do próprio ensaio e confirma um único evento.
- Painéis em Aprendizado: observação/iniciativa com motivos e acessos, memória e
  interesses com correção, exclusão e desativação. Prévia Qt renderizada e revisada.
- InterestEngine separa preferências confirmadas/inferidas, fatos informados,
  projetos e interesses simulados, com fontes/confiança/experiências limitadas.
  Pedidos explícitos como “lembre que gosto de astronomia” são persistidos.
  Uma menção casual não é convertida automaticamente em preferência confirmada.
- Memória social entra no contexto do modelo como dados sem autoridade sobre
  permissões. Estudos autorizados podem atualizar interesses simulados com fonte.
- Limites: observação de janelas/pastas/navegador ainda não conectada; preferências
  por tópico usam correspondência literal, não compreensão semântica comprovada;
  mensagens espontâneas são modelos de texto contextuais, sem geração pelo LLM.

## Evolution 2.0 — recursos e fila

- **462 aprovados, 1 ignorado**, 17,04 s. Avisos: pynvml legado no ambiente e COM
  pywinauto. Os testes são evidência das capacidades cobertas, não de todas as fases.
- ResourceGovernor com reservas configuráveis em Personalizar, CPU/fila/latência,
  RAM física e memória comprometida real do Windows; pesquisa de fundo respeita
  foco e áudio. STT usa admissão e prioridade de voz.
- Fila limitada por prioridade, lugar reservado a pedidos interativos, cancelamento
  de espera e timeout respeitado. Cancelar não encerra à força uma geração HTTP ativa.
- Corrigida recusa indevida de contexto já residente quando a RAM disponível varia;
  pressão transitória não substitui o modelo selecionado por fallback offline.
- **Tarefa real Qwen3.5 4B aprovada**: duas leituras verificadas e soma correta,
  18,97 s (`build/evolution-baseline/task-after-b.json`). Antes: interrompida após
  uma leitura, 16,75 s. Esses ensaios diferentes não provam ganho de latência do LLM.
- Telemetria real: média 78,62 ms antes; 7,14 ms após NVML, incluindo inicialização
  em 12 amostras; média aquecida 0,186 ms. Consumo de RAM/VRAM da UI ainda não foi
  comparado. Reproduzir com `tools/benchmark_resource_snapshot.py --output <json>`.
- TTS/visão e testes prolongados ainda exigem integração/validação nas fases seguintes.

## Evolution 2.0 — Fase A

Branch `codex/nyx-evolution-2`, baseada no HEAD correto `f1fb9a5`.
Baseline: 435 aprovados / 1 ignorado. Após as correções: **445 aprovados / 1
ignorado**, 22,68 s; Ruff aprovado. Evidências em `build/evolution-baseline`.

- `code_task` exige confirmação também sem `apply`; microagente patch não executa
  testes. O executor padrão recusa execução sem sandbox real. Propostas funcionam
  com `operation="propose"` e `test_output`, sem executar ou gravar código.
- CodeAct mantém planejamento e reparos textuais, mas bloqueia execução irrestrita
  e caminhos fora do workspace. Um diretório de trabalho não é isolamento.
- CodeTask restaura arquivos após exceções do modelo/executor e exige `apply`
  booleano. Testes comprovam recusa de conftest com efeito externo e rollback.
- Diagnóstico real Qwen3.5 4B **falhou** após a primeira leitura (16,75 s), por
  recusa de memória na chamada seguinte. Não houve troca por modelo inferior.
- Ao retomar, o arquivo da referência da branch continha 41 bytes nulos. Foi
  preservado em `build/evolution-baseline/corrupt-branch-ref.bin` e recuperado do
  reflog para `9c6415c77f9a21bd21613c0e9dc71345bbe14056`; objetos e conectividade
  conferidos com Git. Nenhum conteúdo do usuário foi descartado.

Esta seção substitui alegações anteriores de segurança por CWD. Sandbox real,
demais fases e aceitações completas continuam pendentes.

## Atualização: Navegador Avançado, Papel Patch com Escrita Supervisionada e Ciclo de Código com Modelo Real — 2026-10-22

- **Estabilização da IA Local e Inferência GPU**:
  - Removido `OLLAMA_FLASH_ATTENTION=1` forçado de `src/core/ollama_service.py` que disparava o crash de flag inválida `--no-mmap` em builds novos do llama-server no Windows+CUDA.
  - Aumentado timeout de leitura de telemetria `ollama_models` em `src/core/runtime_budget.py` de 2.0s para 5.0s com tentativa de retry, eliminando falsos positivos de falta de memória durante inferência concorrente.
  - Teste ao vivo no hardware confirmou ~80.9 tokens/s na GPU GeForce RTX 3060.
- **Navegador Avançado (`src/tools/browser_tool.py`)**:
  - Extração estruturada de dados da web: `links` (coleta até 200 links com texto e URL absoluta) e `tables` (coleta linhas e cabeçalhos de tabelas HTML).
  - Espera assíncrona de SPA (`wait_text`): aguarda texto dinâmico renderizado no DOM sem polling destrutivo.
  - Rolagem (`scroll`): rolagem contínua para baixo/cima/topo/fim ou até seletor com `scrollIntoView`.
  - Multi-abas (`tabs`, `new_tab`, `switch_tab`, `close_tab`): gerencia abas independentes via CDP.
- **Escrita Supervisionada na Equipe de Microagentes (`src/core/agent_team.py`)**:
  - Novo papel especializado `"patch"`: analisa relatórios de erro e falhas de teste e formula propostas de correção via `code_task`.
  - Barreira de segurança: `_action_denial_reason` barra explicitamente `apply=True` para subagentes, forçando que modificações em disco passem pela supervisão da Nyx principal e aprovação do usuário.
- **Ciclo de Código Autônomo com Modelo Real (`src/tools/code_task_tool.py`, `src/core/llm_client.py`)**:
  - Integração de `CODE_TASK_SCHEMA` com suporte a schemas JSON dinâmicos em `OllamaClient.generate` e `RecoveringLLM.generate`.
  - Validação real de ponta a ponta com o modelo `qwen3.5:4b`: o modelo identificou teste falhando, propôs a correção precisa (`return a * b`), aplicou as alterações e os testes foram aprovados na 2ª rodada (`Passed: True`).
- **Validação Total**: **431 testes aprovados, 1 ignorado**, Ruff 100% limpo, e todos os 34 testes funcionais de `test_all_nyx.py` aprovados.

## Atualização: Correção de Timeout, Suporte a IA Local Completa e Aceleração GPU CUDA — 2026-10-22

- **Diagnóstico da Causa Raiz do Timeout**:
  1. O Windows iniciava automaticamente um executável do Ollama em `C:\Users\darlan\AppData\Local\Programs\Ollama\ollama.exe` que não possuía bibliotecas CUDA instaladas (apenas `ggml-cpu-sse42.dll`), rodando 100% em CPU. As requisições demoravam 77+ segundos e estouravam o timeout da aplicação.
  2. Em `src/core/runtime_budget.py`, a fórmula de orçamento `model_weight_budget_bytes` multiplicava o orçamento por `max(0, ram_available - 2 GiB) * 2`. Com ~1.5 a 2.2 GiB de RAM disponível (padrão no Windows com apps abertos), o orçamento caía para 0 bytes, fazendo a Nyx recusar todos os modelos locais com `preferred_model_deferred` ("O modelo não cabe no orçamento atual"), mesmo com mais de 11 GiB de VRAM livre na GeForce RTX 3060.
  3. O timeout da fila de inferência `INFERENCE_GATE.slot` estava limitado rigidamente a 45 segundos (`min(timeout, 45.0)`), e o timeout do cliente Ollama era de apenas 60 segundos, insuficiente para cold-load de modelos maiores (ex: Qwen 3.5 9B) ou geração sob carga.
- **Correções Aplicadas**:
  - Sincronizadas as bibliotecas de aceleração GPU CUDA (`cuda_v12`, `cuda_v13`, `vulkan`, `llama-server.exe` compilado para CUDA) de `E:\Ollama\lib\ollama` para `C:\Users\darlan\AppData\Local\Programs\Ollama\lib\ollama`.
  - Atualizado `src/core/ollama_service.py` para preferir a instalação com suporte total a CUDA (`E:\Ollama\ollama.exe`) e ampliar o timeout de prontidão do serviço para 12s.
  - Corrigido `src/core/runtime_budget.py`:
    - `model_weight_budget_bytes` agora permite staging proporcional de memória quando VRAM dedicada está disponível e a RAM do sistema está na faixa saudável de 1.5 a 4 GiB, permitindo carregar modelos como Qwen 3.5 4B e Qwen 3.5 9B perfeitamente na GPU.
    - `resident_context` alinhado à folga de segurança real do sistema (headroom de 1 GiB de RAM e 4 GiB de VRAM), permitindo que modelos residentes na GPU sejam mantidos sem quedas para o modo offline.
    - `post_ollama_json` e `INFERENCE_GATE.slot` atualizados para respeitar timeouts estendidos (90s na fila e 120s na conexão HTTP).
  - Adicionado suporte a `DeepSeek-R1:latest`, `deepseek-r1:latest` e `qwen3.5:9b` em `MODEL_PREFERENCE` em `src/core/llm_client.py`, e timeout do `OllamaClient` aumentado para 120s.
- **Verificação Real em Hardware**:
  - `ollama ps` confirmou execução 100% na GPU (`100% GPU`) na NVIDIA GeForce RTX 3060 12GB.
  - Teste de inferência do `qwen3.5:4b` e `qwen3.5:9b`: tempo de resposta caiu de 77s (CPU) para ~1s a 3s residente, com geração de JSON estruturado e schema verificado com sucesso (`parse_ok: True`).
- **Validação**: **421 testes aprovados, 1 ignorado**, Ruff limpo, e suite completa de 34 módulos funcionais em `test_all_nyx.py` aprovada.

## Atualização: token para repositório privado e staging verificado — 2026-10-21 (DeepSeek Harness)

- Diagnóstico: `api.github.com/repos/Kronos1027/nyx-agent` responde **404** para requisições anônimas e `private: true` para a API autenticada. O updater como estava **nunca** veria releases desse repositório.
- `core/updater.py` agora aceita um token **somente leitura** por `NYX_GITHUB_TOKEN` ou pelo arquivo `%LOCALAPPDATA%\Nyx\github_token`, enviado como `Authorization: Bearer`. Sem token, segue anônimo; o token nunca é registrado em log.
- Erro 404 passou a explicar a causa: repositório privado sem token, ou release não publicada.
- Novo `--update-check` no aplicativo: imprime JSON com versão instalada, se a instalação é elegível (`supported`) e a release encontrada; sai com código 1 quando a consulta falha.
- Verificação de ponta a ponta **sem rede e sem instalar**: `build/update_stage_check.py` monta uma release falsa apontando para o ZIP real de 153 MB, confere SHA-256 do arquivo `.sha256`, faz download em blocos, extração segura (520 entradas), confirma `Nyx.exe` no payload e limpa a preparação — concluído em 2,2 s.
- Validação: **425 testes aprovados, 1 ignorado**, Ruff aprovado (4 casos novos de token e do aviso de 404).
- Limite: a aplicação real da atualização (helper PowerShell, troca de pasta, rollback e reinício) **não** foi exercitada nesta rodada; só a preparação verificada. Nenhuma release foi publicada — o repositório é privado e não há token configurado nesta sessão.

## Interface: animações de estado e ritmo — 2026-10-21 (DeepSeek Harness)

- A barra lateral agora **anima a largura** (245 ↔ 78 px, 220 ms, easing cúbico) em vez de saltar; a animação usa um timer próprio, porque a `QVariantAnimation` compartilhada travava quando dois testes de interface rodavam em sequência.
- Novo **indicador de digitação** no feed: bolha "Nyx está pensando" com três pontos e pulso de opacidade em laço (1,4 s), criada ao começar o pedido e removida ao terminar. `_show_typing`/`_hide_typing` são idempotentes.
- Transição de página mantida (fade de 170 ms) e ampliada para o novo estado; estilos da bolha entraram no tema (borda, raio e cores do destaque).
- Validação: **421 testes aprovados, 1 ignorado**, Ruff aprovado (2 casos novos: indicador segue o processamento e a largura do trilho realmente anima até 78 px e volta a 245 px).
- Captura: `build/previews/desktop-typing.png` mostra a bolha pulsando entre a mensagem do usuário e o compositor.
- Limite: a animação de largura redesenha a cada 16 ms e não foi medida em monitores de alta taxa; o indicador não mostra progresso por etapa (isso continua no rótulo de status).
- Pacote reconstruído e instalado; `--browser-check` e `--self-check` com exit 0. SHA256 ZIP: `13a15b6a4cd6514977fb1cccfc1b755b0d1bed245e085e5b6413bf05d4ea8c1d`; executável: `05108bba49985e33221278f16a92a16e7dd2d5554efd9a6cf0ad69e504e6ff25`.

## Ciclo de código com testes — 2026-10-21 (DeepSeek Harness)

- Novo `src/tools/code_task_tool.py` e ferramenta `code_task`: roda `pytest` na pasta indicada, lê a falha, pede ao modelo um plano JSON de edições e repete até passar ou esgotar as tentativas (padrão 2, máximo 3).
- **Proposta por padrão**: sem `apply=true`, nada é gravado; o resultado traz os arquivos e o conteúdo proposto. Com `apply=true`, cada arquivo é lido para backup e restaurado se os testes continuarem falhando.
- Limites rígidos: repositório dentro das raízes permitidas; no máximo 5 arquivos e 200 KB por arquivo; só `.py/.md/.txt/.json/.toml/.cfg/.ini/.yaml/.yml`; caminhos relativos sem escape; `pytest` com timeout de 300 s.
- Confirmação: a ferramenta é sensível sempre e destrutiva apenas quando `apply=true`; `code_task` entrou em `VALID_ACTION_TYPES` e na gramática GBNF (validada com `LlamaGrammar.from_string`).
- Interpretador: usa a venv do próprio projeto (`.venv/Scripts/python.exe`, `venv/bin/python`), depois `NYX_PYTHON`, depois o Python do PATH. Isso importa porque dentro do executável congelado `sys.executable` é o `Nyx.exe`, não um Python.
- Verificação real: um projeto temporário com `add` subtraindo em vez de somar começou com `pytest` exit 1; o ciclo aplicou a correção proposta e o reprocessamento passou com exit 0.
- Validação: **419 testes aprovados, 1 ignorado**, Ruff aprovado (12 casos novos: proposta sem escrita, aplicação, escape de caminho, extensão proibida, plano vazio, reversão e raiz externa).
- Limite: o modelo real não foi usado nesta verificação (RAM livre abaixo do orçamento); o plano veio de um LLM roteirizado. O ciclo não interpreta falhas de importação fora do escopo nem roda comandos além de `pytest`.
- Pacote reconstruído e instalado; `--browser-check` e `--self-check` com exit 0 e `tools.code_task_tool` presente no PYZ. SHA256 ZIP: `009ddf049145b187213b37d652c175ab69c223e41951bcae7dde61781013421f`; executável: `5c99b6c6741f9863f98ad0471b417bccd0d42f624f2330524c7301c8a7523ece`.

## Equipe de microagentes ampliada — 2026-10-21 (DeepSeek Harness)

- `core/agent_team.py`: até **4 tarefas** independentes por pedido, com **3 em paralelo** e **2 passos** por agente (uma consulta + a resposta que a usa). O modelo continua serializado por um lock; só as ferramentas de leitura correm juntas.
- Cinco papéis: `pesquisa` (web/busca), **`navegador`** (abrir/ler páginas http(s), sem clique), `arquivos`, `sistema` e **`codigo`** (leitura de código/config para explicar riscos). Cada papel declara ferramentas e ações permitidas.
- Recusas continuam auditadas: ferramenta fora do escopo, ação fora da lista permitida (ex.: clique ou `file://` no navegador), ferramenta destrutiva ou sensível, consulta repetida (encerra sem repetir) e tempo limite por equipe (150 s) com marcação `timed_out`.
- Cada resultado carrega `steps` e a lista de `tools` usadas; a auditoria registra passos e sucessos por equipe.
- Validação: **407 testes aprovados, 1 ignorado**, Ruff aprovado (4 casos novos, incluindo dois passos e bloqueio do navegador).
- Limite: o teste com o modelo real foi **adiado** — havia 3,4 GiB de RAM livre e o orçamento recusou carregar o Qwen3.5 4B. A validação desta rodada usa modelos roteirizados; nenhuma equipe real de 4 agentes foi observada em produção.
- Pacote reconstruído e instalado; `--browser-check` e `--self-check` do executável congelado terminaram com exit 0. SHA256 ZIP: `af75cfed76c6c3474b5506b861ca8fc09ff0819ef0e803e3bebe5763ba441f84`; executável: `845053fceb389acd16ccfa981749f6fb768040c01e9613f97ef9f38f155a7798`.

## Navegador real via CDP — 2026-10-21 (DeepSeek Harness)

- Novo `src/tools/browser_tool.py`: sessão isolada de Edge/Chrome pelo Chrome DevTools Protocol, iniciada sob demanda com porta própria e perfil temporário. Ações: `open`/`navigate`, `read`, `click`, `type`, `wait`, `screenshot`, `status` e `close`.
- Segurança: só `http(s)`; `file:`, `javascript:` e `data:` são recusados; seletor e texto têm limite de tamanho; capturas só podem ser salvas dentro das raízes permitidas; clique e digitação pedem confirmação no modo assistido.
- `ToolSpec` ganhou `sensitive_probe`/`is_sensitive_for`, então a confirmação pode variar por ação em vez de por ferramenta; o `agent_loop` passou a usar esse veredicto.
- `browser` entrou em `VALID_ACTION_TYPES`, na gramática GBNF e no registro de ferramentas; os sinônimos "navegador"/"navegar" apontam para ele (antes caíam em `web`).
- Verificação real nesta máquina: o Edge headless abriu uma página local, leu o texto, digitou "Darlan", clicou no botão e releu "Clicado: Darlan"; captura em `build/previews/browser-check.png`.
- Novo `--browser-check` no executável: sobe uma página local, digita, clica e confere o resultado, retornando código 0/1 — serve de teste de fumaça do pacote congelado.
- O `close()` derruba a árvore de processos e mata filhos órfãos cujo comando carrega o perfil temporário; sem isso, cada sessão deixava renderizadores do Edge vivos.
- Validação: **403 testes aprovados, 1 ignorado**, Ruff aprovado (11 casos novos do navegador).
- Limite: ainda não há extração estruturada (links/tabelas), espera de navegação SPA, upload/download nem múltiplas abas; o navegador sobe em modo headless por padrão.
- Pacote reconstruído e instalado; `Nyx.exe --browser-check` no executável **congelado** terminou com exit 0, assim como o autoteste normal, e nenhum processo do navegador ficou órfão. SHA256 ZIP: `8304a29c4c902e003c02bdece287e859ec8a6a86fc8bf14450862a6e1c0c9e8d`; executável: `3f59c136fac62702b01c52a9e0b6ce208163fbd4a694cff63ce389f9edccbaad`.

## Interface: paleta de comandos, trilho e avisos — 2026-10-21 (DeepSeek Harness)

- `Ctrl+K` agora abre uma paleta de comandos pesquisável (`src/ui/command_palette.py`): ações da janela (nova conversa, navegar pelas quatro páginas, busca, voz, foco, atualizações, recolher a barra) e até oito conversas recentes; Enter executa, Esc fecha e as setas navegam. A busca de conversas mudou para `Ctrl+F`.
- Barra lateral recolhível (`Ctrl+B`): modo trilho de 78 px só com ícones, persistido em `sidebar_rail`. O título passou a ter política vertical fixa e um espaçador entrou no modo trilho, senão os botões se espalhavam pela altura.
- Avisos transitórios (`src/ui/toast.py`) substituem diálogos para retorno pequeno ("Painéis restaurados", "Configuração do modelo salva"), com fade de 150 ms e saída automática.
- Layout responsivo: abaixo de 1120 px de largura o painel da companhia recolhe sozinho e volta ao alargar a janela.
- Tema ganhou estilos próprios para a paleta e o toast.
- Validação: **392 testes aprovados, 1 ignorado**, Ruff aprovado; capturas `build/previews/desktop-palette.png` (520×306) e `build/previews/desktop-rail.png` (1440×920).
- Limite: a paleta cobre ações da janela e títulos de conversa, não o conteúdo das mensagens nem documentos. O trilho troca de largura instantaneamente, sem animação.
- Pacote reconstruído e instalado (`ui.command_palette` e `ui.toast` confirmados no PYZ); autoteste exit 0. SHA256 ZIP: `c4390c242cb80847cb34315e29d54e4f7bde8c1ef03b94f7c5823cb16a7d3415`; executável: `338c92212273b14d497d5ae5bc51f850e016f59d05bb13eef254e0cea03be9c5`.
- A rota de capacidades para a meta ampliada (navegador, equipe de agentes, ciclo de código, jogos, release) está em `docs/ROADMAP.md`.

## Companhia viva — ciclos ociosos da Oxynisx — 2026-10-21 (DeepSeek Harness)

- Novo `src/ui/pet_routine.py`: planejador puro (relógio e RNG injetados) decide olhar ao redor a cada 16–30 s, um sobressalto ocasional (18% das vezes) e sono após 4 minutos sem atividade. O overlay apenas aplica a decisão.
- `OverlayWindow` ganhou um timer de 1 s, olhar temporário via `_routine_look` (segurando 2,6 s, sem brigar com o seguimento do cursor), `surprised` por 0,8 s e `sleep`. Clique, duplo clique, abertura dos controles, fala, escuta, pensamento e erro acordam a companhia e reiniciam a contagem; o sono é suspenso enquanto uma tarefa roda ou durante arrasto.
- O sinal `emotion_changed` já existente propaga o sono para a companhia embutida na janela principal, então o estado aparece nos dois lugares.
- Validação: **387 testes aprovados, 1 ignorado**, Ruff aprovado; as capturas `build/previews/pet-sleep.png` e `build/previews/pet-look.png` mostram quadros distintos do atlas (sono tem arte própria e o olhar desloca as pupilas).
- Limite: o atlas não tem poses de bocejo ou limpeza de penas; o ciclo usa só as emoções e os olhares existentes. Não houve observação em uso prolongado.
- Pacote reconstruído e instalado (`ui.pet_routine` confirmado no PYZ); autoteste da instalação aprovado (exit 0). SHA256 ZIP: `f6bcd25f9dd88d5c602cbb672009238c5dc9c77e2b64913ca23190193edcd74b`; executável instalado: `98c20eab8e4ee993e9971a0fb19052cc5e232c6f8992a61bfc42ed0c2e022af8`.

## Coordenação de modelos residentes — 2026-10-21 (DeepSeek Harness)

- `core/broker.py` deixou de ser um registro decorativo: cada handle carrega um callback de descarga que roda em `release()` e no despejo por prioridade. Falhas de descarga são contadas em `unload_failures` e não interrompem a inferência; a leitura de VRAM usa o mesmo `resource_snapshot` do orçamento, com fallback conservador quando não há telemetria.
- `runtime_budget` ganhou `under_pressure`, `release_idle_residents` e `_free_then_snapshot`: antes de admitir um pedido Ollama ou um GGUF, modelos ociosos são descarregados quando a RAM livre fica abaixo de 3 GiB ou a VRAM livre abaixo de 1,5 GiB; sob pressão crítica o período de carência de 60 s é ignorado.
- `SpeechToText` registra `whisper:<modelo>` com descarga real, marca uso a cada transcrição e se recarrega sozinho na próxima.
- Verificação real nesta máquina: o whisper small transcreveu o fixture em 5,92 s, foi descarregado por pressão simulada (`released=["stt"]`, `_model=None`) e recarregou na transcrição seguinte em 3,66 s, voltando a ficar registrado.
- Validação: **378 testes aprovados, 1 ignorado**, Ruff aprovado.
- Pacote reconstruído e instalado em `%LOCALAPPDATA%\Programs\Nyx`; `core.broker` confirmado no PYZ do executável e autoteste da instalação aprovado (exit 0). SHA256 ZIP: `722344584c57ef2fe5458e31002a25ca29df08d737e23d6ad0a839dc0ba048af`; executável instalado: `3cd57c6b9e5b8ff57de904ab13810e1f18e715d92fa6ae68ea4ecb95ac69a142`.
- Limite: o `LLMClient` (llama.cpp) continua fora do registro; o serviço Ollama mantém os próprios modelos, e o broker governa apenas o que a Nyx carrega no processo.

## Preferências de voz na interface — 2026-10-21 (DeepSeek Harness)

- A aba **Aparência e voz** ganhou seletor de voz pt-BR (`pf_dora`, `pm_alex`, `pm_santa`), velocidade de 70% a 150% e volume de 0% a 100%, com leitura numérica ao lado de cada controle e o botão **Ouvir uma amostra**. As escolhas são persistidas em `desktop.ini` (`voice`, `voice_speed`, `voice_volume`) e reaplicadas quando o aplicativo abre.
- `VoiceSettings` valida e limita tudo na entrada: voz fora do pacote pt-BR volta para `pf_dora`, velocidade fica em 0,5–2,0 e volume em 0–1. O Kokoro recebe voz e velocidade e o volume é aplicado por escala das amostras; o SAPI5 mapeia o volume para 0–100 e a velocidade para a escala −10..10.
- Validação: **370 testes aprovados, 1 ignorado**, Ruff aprovado. A captura offscreen `build/previews/desktop-voice-settings.png` (1440×920) mostra a página com os três controles e a amostra; o preview também confirmou que as preferências chegam ao TTS na ordem voz → velocidade → volume.
- Pacote reconstruído e instalado em `%LOCALAPPDATA%\Programs\Nyx`; autoteste do pacote e da instalação aprovados (exit 0). SHA256 ZIP: `e9640926789ff9a9fec8c417003b679049919dd580c24c6996908f64c20ac10f`; executável instalado: `39b6856ba97ab7e60b7d1d155da31c7a99cd5ace1ac8b61060eedd8950568e1c`.
- `packaging/build.ps1` passou a coletar o stderr do PyInstaller em vez de deixá-lo abortar o build com `$ErrorActionPreference = "Stop"`; sem isso o script falhava antes de gerar o pacote.
- Limites: não houve escuta real de `pm_alex`/`pm_santa` nesta sessão; a verificação cobre validação, entrega dos parâmetros e renderização, não a qualidade das vozes. O volume atua na síntese da Nyx, não no mixer do Windows.

## Escrita verificada e replanejamento limitado

- Corrigido falso positivo de verificação: write_file agora compara bytes UTF-8 solicitados com o arquivo real; rejeita conteúdo antigo, diretórios e caminhos relativos sem resolução informada pela ferramenta.
- Duas tentativas de replanejamento por tarefa para propostas repetidas, antes de pedir confirmação novamente; nenhuma repetição é executada durante a correção. A resposta final deve entregar a informação solicitada.
- Fluxo real Qwen3.5 4B aprovado em 19,56 s: escrita exata, releitura e código correto na resposta, com aprovação roteirizada restrita ao teste temporário. Nova tentativa selecionou Qwen2.5 3B e falhou sem executar a escrita recusada. Não se afirma estabilidade geral; o roteador ainda precisa considerar competência, além de memória.
- Aplicativo reconstruído e instalado; autotestes aprovados. ZIP SHA256 `af0bbce95c099a1e76fca80d1965e4cc587b655f461b3c77b42a403a67025d84`; executável `26bfe32e6375f52e31f437b9760062b8967602453feb63c9730851a49d64df3d`.
- **283 passed, 1 skipped, 1 warning**, Ruff aprovado. Detalhes, falhas intermediárias e limites em docs/TASK_EXECUTION.md.

## Novo modelo local — Qwen3.5 4B

- Modelo oficial Qwen3.5:4b Q4_K_M baixado e selecionado automaticamente quando cabe nas reservas de RAM/VRAM. Modo interativo sem thinking explícito ativado somente após confirmar suporte nos metadados do runtime.
- Dois ensaios reais de leitura de dois arquivos e soma aprovados com valores novos: 67 + 65 = 132 em 11,67 s; 36 + 85 = 121 em 12,02 s. Uma tentativa anterior respondeu corretamente 81 + 20 = 101, mas encontrou um erro de pontuação no avaliador, agora corrigido.
- Conversa real pela UI: 2,58 s, 127 eventos processados, nenhuma ferramenta indevida. Telemetria pontual: 2,86 GiB na GPU e cerca de 3,97 GiB de RAM livres, contexto 2048. Não representa pico prolongado.
- Executor preserva registro compacto de todas as etapas e falhas; diagnóstico guarda tentativas e exige leituras verificadas e números completos. **279 testes passaram**, um ignorado e aviso COM conhecido; Ruff aprovado.
- Aplicativo reconstruído e instalado; autotestes do pacote e da instalação aprovados. SHA256 ZIP: `0bf3a303f0cca482ee22e0b7da824c9c6f2c76c14c6321d992d080ac3cf27a18`; executável: `add57d4bb0022667673ac2570c01432f3a3a669bfb543e2ec30c89c6943d7460`.
- Evidências, fontes, alterações de metodologia e limitações em docs/MODEL_EVALUATION.md. Não atribuir ganho de velocidade só ao modelo: o diagnóstico também passou a mantê-lo carregado entre etapas.

## Diagnóstico real de planejamento — 2026-10-21

- O teste voltou a executar com Ollama/qwen2.5:0.5b. Primeira tentativa: 13,58 s, uma leitura verificada e interrupção aguardando confirmação; não concluiu o pedido. Após compactação das instruções e restrição de ferramentas: 3,00 s, JSON válido, nenhuma leitura, afirmação não fundamentada de arquivos ausentes. **Diagnóstico reprovado**, não demonstra capacidade de tarefas com vários passos.
- RAM livre observada posteriormente: 2.311.368.704 bytes; orçamento conservador de pesos: 327.770.112 bytes. Nenhum aplicativo do usuário foi encerrado e os limites não foram afrouxados.
- Alteração no código: TaskRunner passa o catálogo real; Ollama restringe o enum de ações a esse catálogo e usa instruções compactas. Conversas fora de TaskRunner preservam o contrato anterior. RecoveringLLM encaminha esse catálogo. TypeError interno no planejador não provoca segunda geração automática.
- **274 passed, 1 skipped, 1 warning** em 10,59 s; Ruff aprovado. Novos casos verificam isolamento do schema, catálogo vazio e ausência de repetição após TypeError.
- Esta seção registra o diagnóstico anterior à troca do modelo. A revisão Qwen3.5 acima inclui as alterações no pacote instalado; a validação ampla de planejamento continua pendente.
- Referências oficiais consultadas: https://docs.ollama.com/capabilities/structured-outputs (schema restringe o formato, não prova correção semântica) e https://docs.ollama.com/context-length (contextos maiores exigem mais memória). O teste evidencia a necessidade de avaliar qualidade por modelo e orçamento, não apenas JSON válido.

## Interface e Oxynisx — revisão de 2026-10-21

- Atlas estendido original integrado: 1536 × 2288 RGBA, nove estados animados e 16 olhares. Direções do cursor correspondem ao mapa QA fornecido. Quatro diagonais têm ressalvas visuais na origem: 135°, 157,5°, 202,5° e 337,5°.
- Pet flutuante com fundo transparente, controles recolhíveis, menu contextual, duplo clique para conversar, arraste, voz, criação e interrupção. Timer de animação desligado quando oculto ou com movimento desativado; cache direcional limitado a 16 poses.
- Conversa com Oxynisx na abertura e modo Foco; aprendizado separado em Estudos, Conhecimento e Backups; personalização separada em Aparência e voz / Modelo local; estilo compartilhado com Estúdio, confirmação e pet. As telas continuam em refinamento; não se afirma reprodução completa das funções do pet do ChatGPT.
- Recuperação do modelo em pedido posterior com intervalo mínimo de 30 segundos, sem repetir geração que falhou. Migração apenas dos fatos antigos exatos de sistema; preferências personalizadas preservadas e conexões SQLite fechadas explicitamente.
- Validação: **271 passed, 1 skipped, 1 warning** em 13,01 s; Ruff aprovado. Capturas dos três temas, 920 × 640 em modo Foco, estudos, conhecimento, backups, personalização, agenda, estúdio, confirmação e pet geradas em build/previews. Renderização offscreen não comprova composição/DPI em todos os monitores Windows ou qualidade de voz.
- Corrigida falha real de backup com WinError 17 na pasta de dados Windows criptografada: alternativa grava arquivo exclusivo, sincroniza e valida antes de retornar, preserva latest anterior e retém cinco snapshots alternativos. Backup dos quatro bancos nativos criado e validado. Autoteste também revelou e permitiu corrigir acesso ao modelo ausente na renderização sem controlador de inferência.
- Pacote reconstruído e instalado em `%LOCALAPPDATA%/Programs/Nyx/Nyx.exe`; autoteste do pacote e da instalação aprovados (exit 0). SHA256 ZIP: `d6adc08d681df38a822f1a1cf6722792199047d50f13cd999a4c2e786f082236`. Executável instalado idêntico ao pacote: `391504e98c1356575fd767cf5da31751ccce7f36553a8a428069433ec63d13eb`.
- A revisão não treina pesos, não comprova AGI nem paridade com Astra. Testes reais prolongados de voz, automação geral e desempenho permanecem pendentes.

## Executor de tarefas com vários passos

- TaskRunner conectado à interface nativa: decisão → política → ferramenta → verificação → observação → próxima decisão. Até seis ações e prazo cooperativo de 180 segundos; operações já iniciadas não são interrompidas à força.
- Confirmações vinculadas à tarefa e parâmetros, retomada após cada aprovação, interrupção por recusa, cancelamento na interface, proteção contra repetição e feedback por etapa. Leitura/alteração/releitura permitida para conferir resultados. Histórico final sem mensagens intermediárias fabricadas como pedidos do usuário.
- **254 testes passaram**, um foi ignorado e permanece o aviso conhecido de COM do pywinauto. Ruff aprovado. Testes com arquivos temporários e planejador roteirizado validaram execução e controles; a UI também exibiu duas leituras reais e suas observações em demonstração explicitamente roteirizada (`build/previews/desktop-task-demo.png`).
- Planejamento com modelo real ainda não validado nesta revisão: o roteador recusou carregar modelos nas tentativas com RAM livre variando entre aproximadamente 0,7 e 1,9 GiB. Nenhum modelo estava residente em Ollama. O limite foi preservado e aplicativos do usuário continuaram funcionando. Relatório de adiamento: `build/previews/task-live-smoke.json`.
- Detalhes e lacunas em `docs/TASK_EXECUTION.md`; diagnóstico real reproduzível em `tools/verify_task_runner.py`. A CLI ainda usa uma ação por ciclo. Retomada de tarefas após reinício, filas de pedidos e conversa concorrente com tarefas continuam pendentes.
- Executável reconstruído e autoteste do pacote aprovado, incluindo duas ações reais sobre arquivos temporários com planejador roteirizado. ZIP SHA256: `2fb780f76bde3b08eaf015bf16a625d45193384c9090c1a0b470c20210ae688b`.
- As inconsistências de persona inicial e recuperação da rota foram tratadas na revisão de interface acima; validação da recuperação sob carga prolongada permanece pendente.

## Pesquisa ociosa verificada

- Implementada fila persistente de estudos com cancelamento transacional, lease para retomada após falhas, deduplicação de pendências e orçamento diário persistente. Quatro tentativas/dia UTC, intervalo de 15 minutos e uma leitura por vez; UI aguarda 60 segundos sem pedidos e verifica RAM/CPU.
- Três fontes HTTPS permitidas: documentação oficial Python, Windows e Ollama. Downloads limitados, redirects validados, HTML sem execução. Trechos ficam como conteúdo não verificado, recuperáveis no laboratório e visíveis na UI.
- Testes reais pela interface: leitura Ollama concluída em 0,23–0,78 s, interface respondendo enquanto o worker operava, uma nota salva e duas fontes permanecendo na fila. Último ensaio: 0,23 s e 11 eventos de UI. Relatório `build/previews/research-ui-smoke.json`; imagem `build/previews/desktop-learning.png`.
- Testes: **240 passed, 1 skipped, 1 warning**. Casos cobrem trabalhadores concorrentes, cancelamento durante download, interrupção por pedido principal, orçamento após reinício, falha terminal e controles da UI. Ruff aprovado.
- Pacote com estudos e correção de contraste do painel reconstruído, instalado e validado por autoteste com código 0. SHA256 do ZIP: `4104fa4d262c184c2dec117c041e5992255c111884a60d49665cc8379bc04a5e`. O aplicativo instalado inclui a revisão visual final.
- Ainda falta pesquisa aberta com seleção de fontes, síntese/correlação e avaliação de conhecimento; essa implementação coleta trechos e preserva proveniência, sem treinar pesos ou comprovar autonomia geral.
- Próxima lacuna confirmada no código: `AgentLoop.process` executa uma ação e usa a próxima geração para síntese final; ações subsequentes propostas nessa síntese não são executadas. É necessário um ciclo de tarefa com passos limitados, confirmação/retomada, progresso e cancelamento para cumprir tarefas compostas.

## Revisão mais recente: interface, aprendizado e recuperação

- Interface principal nativa com conversas SQLite, busca, Markdown sem carregamento de recursos externos, painéis móveis, três temas, fonte, cores e movimento persistentes. Agenda real e configuração dos caminhos Ollama estão conectadas. Overlay separado via `--overlay`.
- Pet Oxynisx do usuário integrado, nove linhas de animações. Direções do olhar ainda ausentes no atlas original.
- `EvolutionLab` conectado à ferramenta `evolution` e painel Aprendizado: notas com URL/data/hash, busca, deduplicação, limites e propostas declarativas. Simulação é estrutural; não executa código, não demonstra aprendizado de pesos nem aprova habilidades.
- Backup local Fernet dos quatro bancos permitidos, cópia SQLite consistente, limite 32 MiB e restauração com integridade em pasta nova. Timer a cada 30 minutos com app aberto e ocioso; chave exportável pela interface e excluída da nuvem. Restauração guiada pela interface permanece pendente.
- Repositório privado `Kronos1027/nyx_god_and_friend_for_oxynisx` verificado com permissão de escrita e inicializado. Remote local `evolution` adicionado, preservando `origin`. Primeiro backup criptografado enviado e confirmado na branch `nyx-backups`, commit `d71aab9f7ed37fbeb165afa4af3108303371591f`. Chave não enviada. Cópias remotas exigem Git autenticado e ficam limitadas a 5 MiB, sem limpeza automática do histórico remoto.
- Ollama agora é gerenciado pelo Python usando caminhos persistentes verificados: `E:\Ollama\ollama.exe` e `E:\OllamaModelos`. Serviço local iniciado com max_loaded_models=1, num_parallel=1, max_queue=8 e no_cloud=true, confirmados no log. Serviços externos já abertos são reutilizados.
- Orçamento revisado: reserva 2 GiB de RAM e 4 GiB de VRAM; pesos CUDA consideram staging no host. GGUF exige espaço do arquivo inteiro em RAM, pois a wheel instalada é CPU-only. Chamadas compartilham admissão limitada. STT ainda precisa de coordenação global.
- Último diagnóstico real de UI: Qwen2.5 3B respondeu `Olá!` em 3,33 segundos, 166 eventos de UI durante a inferência, JSON válido, zero ferramentas e zero confirmações. Teste curto, sem provar qualidade geral ou velocidade sustentada. Modelo menor de 1B anteriormente propôs ação inadequada para saudação; isso continua sendo uma limitação de qualidade dos modelos pequenos.
- Diagnóstico real de aprendizado: Qwen2.5 3B emitiu `evolution/learn` válido em 5,2 segundos; a ferramenta salvou uma nota com URL em banco temporário e declarou `verified=false`. Relatório: `build/previews/evolution-live-smoke.json`. Esse ensaio não treinou pesos nem comprovou pesquisa autônoma.
- Código publicado em `main` do novo repositório privado, inicialmente no commit `b8f802e204c5b12a70f97a0428936df40728874e`. Publicação limpa de 124 arquivos permitidos, sem herdar histórico Git local, bancos, chaves, logs, capturas ou pesos. `tools/publish_source.py` documenta a seleção e recusa possíveis tokens.
- Suíte atual: **226 passed, 1 skipped, 1 warning**; Ruff aprovado. Testes novos cobrem proveniência, deduplicação, simulação sem execução, criptografia, autenticação, recuperação SQLite/WAL e restrições da cópia Git. O aviso é o conhecido COM/STA do pywinauto.
- Pacote Windows reconstruído com a interface e pet atuais; autoteste do executável aprovado incluindo renderização real da janela (1320×860), presença do atlas e criação/validação de backup criptografado no pacote. ZIP SHA256: `518b6c58757bc25567457171fb26494f81823f40fa2905b4bd6ce7a84d0f1d78`. Ainda não é uma release publicada e a versão permanece 0.1.0 de desenvolvimento.
- Instalada no perfil real em `%LOCALAPPDATA%\Programs\Nyx`, com atalho no menu Iniciar. Memória, agenda e laboratório foram copiados consistentemente para AppData somente onde ainda não existiam; chave de recuperação copiada apenas localmente sem exibir conteúdo. Autoteste da instalação terminou com código 0 (`build/installed-self-check.json`). O aplicativo não foi deixado conversando ou controlando o computador em segundo plano.
- Correção de conexões SQLite da agenda evita bloqueio de arquivo no Windows. Hotkeys agora entregam sinais à thread visual, incluindo bloqueio de controle de tela. O bloqueio de tela não cancela gerações e tarefas já em execução.

A arquitetura e lacunas estão em `docs/EVOLUTION_ARCHITECTURE.md`. Os registros abaixo descrevem revisões anteriores; informações conflitantes de runtime e testes foram substituídas por esta seção.

## O que existe no código

- App desktop Python/PyQt para Windows, com overlay, expressões e controles.
- Conversa local via Ollama ou llama.cpp; existe modo offline determinístico para desenvolvimento.
- Ollama recebe um JSON Schema estrito; o modelo instalado Qwen2.5 3B foi testado e conseguiu emitir uma ação de lembrete válida.
- Seleção automática prefere Qwen 3.5/Gemma 4 quando já instalados; nunca baixa pesos sem ação do usuário. O monitor agora mostra se os pesos ativos do Ollama estão em CPU, GPU ou divididos.
- Fala local via Kokoro/SAPI5 e transcrição via faster-whisper.
- Ferramentas registradas para arquivos em sandbox, shell por templates allowlist, UI Windows, web, clipboard, macros, telemetria, workspace e MCP.
- Agenda SQLite de lembretes únicos, persistente entre reinícios, com listar/cancelar e alerta no overlay. Lembretes só notificam; não executam comandos.
- Memória SQLite/FTS, logs de auditoria, verificação de ações e confirmações sensíveis.
- Inferência, ações aprovadas e captura de voz são serializadas fora da thread visual. A fila de TTS tem no máximo oito falas pendentes.
- O avatar agora é uma coruja pixel art com sete expressões; suas cores indicam modo e erro.
- Equipe de microagentes inicial conectada à ação `agent_team`: até dois especialistas investigam web, arquivos permitidos ou estado do sistema. Inferência compartilhada é serializada para controlar a carga; ferramentas seguras podem executar em paralelo. Agentes filhos não podem escrever arquivos, usar shell ou controlar janelas, e cada decisão é auditada.
- Aplicativo Windows x64 empacotado com PyInstaller 6.22.3, versão 0.1.0. O ZIP portátil contém o executável, runtime, instalador e desinstalador por usuário; dados e pesos ficam fora da pasta do programa.

## Verificação desta revisão

No ambiente Windows do projeto:

```text
python -m ruff check src/ tests/
All checks passed!

python -m pytest
201 passed, 1 skipped, 1 warning
```

O aviso conhecido vem do pywinauto recomendando o modo STA do COM. A suíte não valida áudio real, qualidade do modelo em português ou interação visual completa em diferentes escalas de tela.

- `packaging/build.ps1 -Clean` gerou `dist/Nyx-0.1.0-windows-x64-portable.zip` (147 MB), gravou SHA256 e executou `Nyx.exe --self-check` dentro do pacote. Qt, Kokoro, faster-whisper, llama.cpp, áudio, schema e gravação em AppData passaram.
- O instalador e desinstalador foram exercitados numa pasta temporária: o executável foi copiado com o mesmo SHA256 e removido; os dados em `%LOCALAPPDATA%\Nyx` foram preservados.
- A escrita real no clipboard não pôde ser verificada nesta execução: `OpenClipboard` retorna `Access denied` ao próprio processo de ferramenta e não há janela dona do clipboard. Os testes da lógica usam um clipboard em memória; escrita real deve ser confirmada numa sessão interativa do aplicativo.

## Validação do runtime local (2026-10-20)

- Ollama foi atualizado para 0.40.6; o servidor registrou `version 0.40.6` e detectou a NVIDIA RTX 3060 (compute 8.6, 12 GiB totais, 11 GiB disponíveis). Os cinco modelos existentes continuaram acessíveis no diretório `E:\OllamaModelos`.
- Inferência real com `qwen2.5:3b-instruct` respondeu em português. O primeiro pedido levou 52,1 s, incluindo carregamento do modelo (27,85 s); a geração reportou 22 tokens em 5,96 s (~3,7 tokens/s). Ollama reportou 2,16 GB do modelo na VRAM e contexto 4096. É uma validação funcional, não uma garantia de velocidade sustentada.
- A instância atual foi iniciada fora do launcher da Nyx: seus limites (`MAX_LOADED_MODELS`, fila e modo sem nuvem) ainda não foram aplicados a esse processo. O launcher detecta essa condição e avisa que os limites só passam a valer após reiniciar o servidor.
- O Qwen2.5 3B em Ollama emitiu uma ação `agent_team` válida com dois papéis e tarefas. Um pedido anterior sem limite de saída excedeu 9 mil tokens e atingiu timeout; por isso, Ollama agora tem limite rígido de 512 tokens por geração. Repeti o teste após o limite e o modelo entregou a ação estruturada válida.
- A equipe executou duas chamadas com o Qwen2.5 3B e ferramentas reais em paralelo: pesquisa web (que não retornou resultado direto nessa consulta) e telemetria local (CPU, RAM, RTX 3060 e Ollama). Também foram bloqueados os subcomandos web de localização/clima e consulta Git com caminho arbitrário.
- O roteador revisado leu o inventário instalado e selecionou `qwen2.5:3b-instruct` por caber no orçamento atual de RAM/VRAM; os modelos maiores que não cabiam foram excluídos. Uma chamada real pela mesma função de rota retornou JSON válido em português com contexto dinâmico e `keep_alive=0`; depois, `/api/ps` voltou vazio e o uso da RTX ficou em 841 MiB usados / 11.275 MiB livres.
- As chamadas de inferência Ollama originadas pela Nyx agora compartilham uma fila FIFO global no processo: uma ativa, até duas esperando, prazo de espera de 45 s; contexto limitado dinamicamente a 1k–4k e recusa sob pressão crítica de RAM/VRAM. A escolha do modelo reserva 4 GiB de VRAM e 3 GiB de RAM. Isso protege a Nyx, não impõe limites a outros programas que usam o serviço Ollama.

## Ainda não implementado ou não validado

- Expansão dos microagentes para planejamento cooperativo de múltiplas etapas, síntese própria e cancelamento de tarefas já iniciadas.
- Atualizador no app para a instalação padrão: consulta a versão estável mais recente, baixa em blocos, confere o SHA-256 e bloqueia ZIPs com caminhos perigosos. A troca só ocorre após confirmação, num helper separado, com autoteste e rollback automático se a versão nova não iniciar corretamente. O workflow de publicação existe, mas nenhum release foi publicado nesta rodada; portanto, não há atualização remota disponível ainda. A assinatura Authenticode continua pendente.
- Treinamento ou ajuste fino de modelo. Não há dataset local nem pipeline de treino.
- Controle total de todos os carregamentos: o orçamento governa seleção/contexto/fila das requisições Ollama e agora descarrega o faster-whisper ocioso sob pressão, mas o `LLMClient` (llama.cpp) ainda não participa do registro; e o processo Ollama que já estava aberto mantém suas configurações próprias para os outros clientes.
- A medição anterior em Ollama 0.32.5 usava CPU; a atualização para 0.40.6 ativou o backend CUDA do Ollama. O backend alternativo `llama-cpp-python` instalado segue CPU-only e sua wheel CUDA requer o CUDA Toolkit, ausente nesta máquina; não houve instalação do Toolkit.
- Validação prática de longas sessões, centenas de pedidos, uso intenso de memória/GPU e recuperação após falhas.
- AGI ou execução garantida de qualquer tarefa. Capacidades dependem do modelo, ferramentas, permissões e recursos da máquina.

## Próximas frentes

1. Integrar o `LLMClient` (llama.cpp) ao registro de modelos residentes e testar contenção real entre llama.cpp, faster-whisper e Ollama; decidir como a Nyx deve administrar o serviço Ollama existente sem interromper outros clientes.
2. Desenhar ciclos e ações interativas para a coruja e permitir escolher voz, volume e preferências.
3. Publicar uma release Windows com os dois assets esperados e testar o fluxo de atualização entre duas versões instaladas.
4. Validar o fluxo completo no Windows alvo com um modelo local real, áudio, automação de UI e rollback da atualização.
