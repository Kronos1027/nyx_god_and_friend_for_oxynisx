# Nyx — estado verificado

Última atualização: 2026-10-21

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
- Controle total de todos os carregamentos: o novo orçamento governa seleção/contexto/fila das requisições Ollama da Nyx, mas `ModelBroker` ainda não coordena cargas de llama.cpp e faster-whisper; e o processo Ollama que já estava aberto mantém suas configurações próprias para os outros clientes.
- A medição anterior em Ollama 0.32.5 usava CPU; a atualização para 0.40.6 ativou o backend CUDA do Ollama. O backend alternativo `llama-cpp-python` instalado segue CPU-only e sua wheel CUDA requer o CUDA Toolkit, ausente nesta máquina; não houve instalação do Toolkit.
- Validação prática de longas sessões, centenas de pedidos, uso intenso de memória/GPU e recuperação após falhas.
- AGI ou execução garantida de qualquer tarefa. Capacidades dependem do modelo, ferramentas, permissões e recursos da máquina.

## Próximas frentes

1. Integrar o orçamento central com cargas de llama.cpp e faster-whisper e testar contenção entre essas cargas; decidir como a Nyx deve administrar o serviço Ollama existente sem interromper outros clientes.
2. Desenhar ciclos e ações interativas para a coruja e permitir escolher voz, volume e preferências.
3. Publicar uma release Windows com os dois assets esperados e testar o fluxo de atualização entre duas versões instaladas.
4. Validar o fluxo completo no Windows alvo com um modelo local real, áudio, automação de UI e rollback da atualização.
