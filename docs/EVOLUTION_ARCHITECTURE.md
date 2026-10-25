# Nyx adaptativa: arquitetura e evidências

## Evolution 2.0: snapshots de projetos

`ProjectSnapshot` captura bytes sob limites, produz manifesto SHA-256 e materializa
somente destinos novos. `windows_files` usa abertura nativa com `OBJ_DONT_REPARSE`
e enumeração por handle. A proteção não depende só de resolver caminhos ou checar
atributos antes da operação; o teste converte uma pasta aberta em junction e verifica
que nenhum acesso subsequente segue o alvo. Exportação ZIP usa o inventário imutável.
O ensaio multifile já executa testes dentro do LPAC, mas correção por LLM e gerência
de projetos no runtime ainda pendem. Ver `PROJECT_SNAPSHOTS.md`.

## Evolution 2.0: protótipo LPAC isolado do runtime

`windows_sandbox` cria perfil efêmero, configura Job e ACLs apenas no staging,
verifica token LPAC e mitigação Win32k antes de retomar o processo. Limites de
memória/CPU/processos e cancelamento têm verificações reais iniciais, com espera
dos handles dos descendentes. O launcher não herda ambiente completo ou handles
arbitrários. A capability `registryRead` permanece opção explícita de diagnóstico.
O Job é associado pela lista de atributos na própria CreateProcess, eliminando
a janela de crash anterior à associação. Um `SandboxJournal` protegido registra
perfis antes de criá-los; recuperação exige a trava exclusiva do supervisor e
limpa somente reservas válidas. Registro só é removido após limpeza confirmada.
Não existe fallback sem isolamento nem registro desse backend como ferramenta.
O contrato final de staging, quota de disco e recuperação de projetos precisa ser concluído
antes de conectar CodeTask, skills ou MCP. Evidências e lacunas estão em
`WINDOWS_SANDBOX_PROTOTYPE.md`.

## Evolution 2.0: equipes com dependências

`task_graph.normalize_tasks` valida até quatro nós identificados, suas referências
e ausência de ciclos. AgentTeam agenda somente nós com dependências bem-sucedidas.
As respostas das dependências têm autoridade `untrusted_observation`; permissões
continuam determinadas pelo papel e pelo registro, inclusive circuit breaker.
O limite de seis chamadas do pedido principal permanece; uma delegação tem seu
próprio limite de quatro agentes/duas etapas cada. Não são seis consultas físicas
somando toda a equipe. O painel e checkpoint guardam os resultados subordinados.

Um token de cancelamento por execução atravessa a fila de inferência e as checagens
de OperationControl nas ferramentas. Expirar encerra a espera do chamador, solicita
cancelamento de pendentes e bloqueia novas ações das threads antigas. Chamadas
bloqueadas já em curso podem continuar até seus próprios timeouts; não há promessa
de término forçado de thread. O registro conserva até quatro futures e impede
nova equipe enquanto houver trabalho anterior vivo. Resultado externo potencialmente
incerto propaga para WAITING_REVIEW do pedido principal. Falta de recursos antes
de ferramentas produz RESOURCE_PRESSURE sem inventar um efeito externo.

Somente consultas de escopo permitido podem se sobrepor. Inferência usa um lock
compartilhado por registro e a fila global; agentes de navegador são serializados
durante toda a investigação para preservar contexto de página. Resultados textuais
não comprovam suas próprias afirmações: o verificador confere recebimento dos
relatórios, separadamente de pós-condições do objetivo. O ensaio local de dependências
usa Qwen real e arquivos temporários reais; testes de falha usam barreiras e eventos
determinísticos. Ainda não há prova de ganho de latência contra uma tarefa simples.

## Evolution 2.0: checkpoints e recuperação

O TaskRunner do desktop usa `TaskJournal` em `data/nyx_tasks.db`, com transações
SQLite e exclusão de escritores por lock do sistema operacional. Persiste PLAN,
ACT (antes de executar), OBSERVE e WAITING_USER. Pausa mantém as etapas e os
limites; pausa não cancela uma operação nativa já enviada. Cancelamento continua
usando OperationControl. O painel aciona a retomada em worker, não na thread Qt.

Ao reabrir, registros não terminais tornam-se PAUSED ou WAITING_REVIEW quando
há ação em voo. A recuperação desconta conservadoramente o tempo desde o último
checkpoint de uma tarefa que estava ativa, incluindo o período desligado.
Pausas registradas não consomem orçamento durante a espera. Confirmações antigas
são descartadas. Efeitos incertos nunca são reenviados: nesta versão a revisão
requer inspeção e novo pedido. Não há reconciliação automática por heurística.

O histórico guarda no máximo 200 tarefas e 128 KiB por registro. Excluir um
registro não desfaz suas ações. Credenciais reconhecidas por chave/padrão são
redigidas; isso não é um classificador completo de segredos em texto livre. O
banco local, como a memória existente, depende da proteção da conta Windows;
o arquivo exportado por BackupVault é criptografado. Dados externos continuam
sem autoridade para alterar permissões. PLANNING_FINISHED distingue o término
da resposta de comprovação semântica do objetivo, ainda pendente nesta fase.

## Evolution 2.0: ações verificáveis e interrupção

`WindowsAutomationClient` inicia sob demanda um auxiliar próprio sem Qt e
serializa pedidos JSON limitados. `UIATargets` mantém descritores e reconsulta
HWND/PID/create_time/runtime ID em COM MTA de vida persistente. O walker limita
80 controles, profundidade quatro e três segundos entre chamadas UIA. O cliente
impõe oito segundos ao pedido inteiro e consulta cancelamento a cada 50 ms;
em falha encerra somente o auxiliar criado por ele. Mutações enviadas sem resposta
têm resultado desconhecido e interrompem TaskRunner, sem repetição automática.
Não é um sandbox para código gerado; só aceita inspeção, foco e ações UIA fixas.
Integração com pacote congelado permanece pendente e falha explicitamente.
Snapshot vence em 30 segundos. Diálogos pertencentes a uma janela são
selecionados por HWND próprio; o ancestral superior de UIA pode ser a janela
dona, por isso a validação usa presença na subárvore consultada, não esse ancestral.

UI Automation/MSS e entrada de mouse usam pixels físicos sob contexto DPI da
thread, restaurado ao sair. Captura informa origem, tamanho e janela/monitor;
localização visual usa essa origem sem dividir por escala global. Nenhuma
captura fica em loop contínuo. Testes reais usam processo Qt dedicado com arquivo
de resultado independente do verificador, sem agir em aplicativos pessoais.
Referências: [coordenadas UIA](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-screenscaling),
[threading e COM UIA](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-threading),
[DPI por thread](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setthreaddpiawarenesscontext),
[padrões de controles pywinauto](https://pywinauto.readthedocs.io/en/latest/code/pywinauto.controls.uia_controls.html).

`OperationControl` pertence ao registro de ferramentas e é compartilhado com
TaskRunner, BrowserSession e UITool. Cancelamento normal admite um novo pedido;
emergência permanece até ação direta na UI. Nenhuma ferramenta recebe API de
retomada. A barreira bloqueia novas chamadas, e CDP checa entre mensagens/esperas;
não se promete interrupção forçada de HTTP, código nativo ou subprocessos ativos.

BrowserSession mantém CDP e usa `Page.navigate.loaderId`/`Page.getFrameTree` para
confirmar o novo documento. O servidor do autoteste é multithread para tolerar
conexões antecipadas do Chromium. Elementos são referenciados pelo objeto remoto:
unicidade/visibilidade, dois retângulos estáveis e hit-test antecedem a entrada.
O DOM é inspecionado por código fixo; os localizadores são dados JSON. Clique usa
Input.dispatchMouseEvent; edição usa teclado/Input.insertText e compara o valor.
Eventos `isTrusted` foram conferidos em fixture local real, não em mocks.

Playwright foi avaliado como referência de locators/actionability, mas não foi
adicionado: CDP já controla o navegador instalado sem baixar outro runtime.
Os locators atuais implementam apenas nomes e papéis DOM comuns; não equivalem
à árvore de acessibilidade completa do Playwright. Frames/shadow DOM exigem
uma extensão explícita futura. Resultados de cliques sem pós-condição ficam
não verificados; texto de página é observação, nunca instrução de segurança.

Referências: [CDP Page](https://chromedevtools.github.io/devtools-protocol/tot/Page/),
[CDP Input](https://chromedevtools.github.io/devtools-protocol/tot/Input/),
[Playwright actionability](https://playwright.dev/python/docs/actionability).

## Evolution 2.0: percepção e iniciativa

`ContextAwarenessEngine` guarda permissões, eventos com TTL/deduplicação e até
500 registros de auditoria em `nyx_context.db`. Callbacks passam pela permissão
antes da coleta, debounce de cinco segundos e supressão sob carga. Sensores
externos permanecem desligados até autorização. O sensor de processos usa
somente PID/nome/data de criação explicitamente escolhidos, distingue PID
reutilizado e não interpreta falta de acesso como encerramento. A UI consulta
esses poucos PIDs no timer de 30 segundos; não é captura de tela nem vigilância
geral. Seleções duram uma sessão.

`ProactiveInteractionEngine` consome eventos em transação SQLite, impedindo
ofertas duplicadas entre chamadas concorrentes. Pontua utilidade, urgência,
novidade e preferência confirmada. Interrupção é uma barreira anterior à
pontuação; não há custo de LLM. Registra motivo/resposta, respeita horários que
cruzam meia-noite e dobra o intervalo após recusa. Histórico de 90 dias mantém
limites entre reinícios. Apagar histórico é uma ação explícita da pessoa.

`InterestEngine` limita 500 registros e oito fontes/experiências por interesse.
Categorias são distintas; hipótese não vira fato por repetição. Pesquisa
autorizada atualiza somente interesse simulado. A memória social é recuperada
em contexto limitado e não pode modificar a política de ferramentas.
Os bancos pessoais continuam ignorados no Git e entram no backup criptografado.

## Evolution 2.0: admissão de recursos

`ResourceGovernor` decide a admissão de trabalho a partir de RAM, VRAM, CPU,
fila e média móvel de latência. Políticas validadas podem ser salvas/carregadas
em JSON; Personalizar permite definir reservas de RAM/VRAM persistentes. Sono suspende
inferência; foco e trabalho interativo adiam atividade opcional. A pesquisa
ociosa usa essa política e respeita foco, escuta e fala.

`InferenceGate` mantém uma geração ativa e dois lugares de espera: ordena por
prioridade e FIFO dentro da prioridade. Trabalho opcional deixa um lugar para
o usuário. `inference_scope` transporta prioridade e cancelamento entre chamadas;
TaskRunner cancela sua espera. Não interrompe à força uma requisição HTTP já
enviada. O timeout configurado é respeitado, sem ampliação silenciosa.

Telemetria GPU usa NVML lazy e leitura fresca; nvidia-smi permanece como fallback.
Contexto já alocado (até 4096 tokens) pode ser reutilizado quando nome, digest e
residência GPU coincidem e as reservas continuam disponíveis. Essa distinção
evita contar a memória residente como uma nova carga. Nenhum modelo é trocado
por pressão transitória. Metadados ausentes não comprovam residência.

Memória comprometida e limite do Windows são medidos via GetPerformanceInfo;
esgotamento de compromisso também impede inferência. STT usa prioridade de voz
e a mesma admissão. Ainda não há arbitração de todos os processos externos,
coordenação integral TTS/visão, preempção de geração ativa ou metas de RAM da interface
comprovadas. O governador não é um limitador global de GPU.

## Princípio

O `SkillManager` permanece um armazenamento declarativo; seu catálogo agora está
conectado ao runtime por `skills` (list/search/get), sem execução interna de etapas.
Agora serializa operações com lock do SO, grava versões exclusivamente e troca
o ponteiro ativo por substituição atômica. Cada versão nova registra o antecessor
ativo para não restaurar arquivos órfãos. Dados retornados são cópias independentes.
Esse histórico não concede permissões nem comprova validação de uma habilidade;
ações propostas a partir das consultas passam pelo fluxo normal de ferramentas.
Pacotes SKILL.md, ativação por habilidade e execução isolada de scripts estão
pendentes. Ver `SKILL_HISTORY.md`.

`SkillPackage` valida SKILL.md com loader YAML seguro e limitado, preservando
scripts/recursos somente como bytes em `ProjectSnapshot`. Exportação inclui raiz
nomeada; leitura textual não executa recursos. Esse componente ainda não habilita
pacotes no catálogo do runtime. Ver `SKILL_PACKAGES.md`.

O Estúdio agora possui um catálogo de projetos separado (`ProjectStore`), com
versões imutáveis de `ProjectSnapshot`, manifesto SHA-256 e limites de espaço.
`ProjectPanel` executa I/O em QThread e só atualiza widgets na thread da interface;
restaurar cria nova versão. Exportação recebe os bytes já verificados, sem executar
ou renderizar HTML. A execução Python legada com privilégios do usuário foi removida.
O catálogo ainda não participa do BackupVault e o painel não inicia LPAC. Detalhes,
limites e evidências em `PROJECT_STUDIO.md`.

O runtime conecta `WorkspaceTool` a um despachante Qt de capacidade um; ele retorna
sucesso somente depois da exibição na thread principal. Expiração/cancelamento
antes da execução descarta o evento; resultado incerto durante a execução usa o
mesmo `outcome_unknown` do TaskRunner. Telemetria do Estúdio roda fora da GUI.
Saída da aplicação preserva o loop Qt até terminar os workers próprios do Estúdio.

A capacidade vem do modelo local, ferramentas observáveis, memória recuperável e avaliação de resultados. Adicionar memória e agentes não equivale a treinar pesos nem demonstra AGI. Não há evidência de paridade com Astra ou de controle perfeito de programas e jogos.

## Circuitos com frequências diferentes

1. **Interação:** UI e voz recebem pedidos; janela continua respondendo durante inferência em worker. Pet mostra estados observados, sem exibir raciocínio interno como prova de capacidade.
2. **Decisão:** modelo produz ação estruturada; registro, política, confirmação e verificador controlam execução. Microagentes compartilham a admissão de inferência; multiplicar agentes não multiplica modelos residentes.
3. **Conhecimento:** notas externas persistem com URL, data e SHA256; deduplicação e limites evitam crescimento irrestrito. Notas são conteúdo não verificado e não podem alterar políticas. Recuperação é explícita via ferramenta evolution/search.
4. **Laboratório:** propostas declarativas de até 12 passos; simulação verifica ferramentas existentes e requisitos de revisão. Nada é executado ou promovido por essa simulação. Código proposto deverá futuramente ser avaliado em VM/Windows Sandbox com limites e fixtures confiáveis; subprocesso comum não oferece isolamento suficiente.
5. **Evolução futura:** dataset de episódios verificáveis → avaliação externa ao candidato → comparação de taxa de sucesso, latência e memória → versão candidata → implantação gradual → rollback. Testes escritos pelo próprio candidato não bastam. Treino de pesos exige pipeline separado, dados permitidos e medição contra conjunto reservado.
6. **Recuperação:** snapshots consistentes SQLite, criptografia Fernet autenticada, limite 32 MiB local/5 MiB nuvem. GitHub recebe só latest.nyxbackup e README na branch nyx-backups. Chave separada em data/backup-recovery.key, exportável pela interface; não é enviada. Quem possui essa chave consegue ler o backup. Não há recuperação sem chave.

## O que existe nesta revisão

- Fila persistente de estudo ocioso no mesmo banco do laboratório: currículo inicial Python/Windows/Ollama, inclusão e cancelamento pela UI ou ferramenta evolution. Inicia após 60 segundos sem pedidos à Nyx, com pelo menos 2 GiB livres e CPU abaixo de 85%; limita quatro tentativas/dia UTC e intervalo mínimo de 15 minutos. Não depende de inferência adicional.
- Download HTTPS limitado a 512 KiB, com prazo e timeout, apenas dos três hosts de documentação permitidos e com redirects validados. Não executa JavaScript nem conteúdo recebido. Guarda até 5800 caracteres extraídos como conteúdo externo não verificado; ainda não produz síntese, comparação de fontes ou compreensão demonstrada.
- Lease e orçamento transacionais impedem trabalho duplicado concorrente; cancelamento e commit da nota são serializados no banco. Trabalho interrompido pode ser retomado após expiração da lease e respeita o orçamento persistente. Falhas terminam com estado visível, sem retentativa infinita.
- Painel de estudos mostra fila, fonte e prévia textual do que foi coletado. Não faz vigilância geral da atividade do usuário: o critério de intervalo observa pedidos à Nyx, CPU e RAM.

- EvolutionLab com notas de fonte declarada, busca literal, deduplicação, propostas limitadas e simulação estrutural. Está conectado ao schema, personalidade, registro de ferramentas e painel Aprendizado.
- BackupVault recupera cópia consistente dos quatro bancos permitidos, confere autenticação e integridade SQLite e restaura em pasta nova; não substitui bancos abertos. A UI cria backups e exporta a chave. Restauração ainda usa a API Python e precisa de uma experiência guiada.
- CloudBackup usa credenciais do Git já configuradas, sem extrair tokens, sem interação de login e sem force push. Branch separada preserva desenvolvimento. Falha remota deixa cópia local e aviso; divergências exigem reconciliação. Git deve estar instalado no computador de destino. Não há retenção automática do histórico remoto: versões anteriores permanecem no Git e consomem espaço.
- Timer de backup a cada 30 minutos enquanto a interface estiver aberta, adiado durante pedido ativo. Cópia remota pode ser desativada no painel. Não é serviço permanente do Windows nem sincronização de vários computadores.
- Pet Oxynisx integrado a partir do spritesheet local gerado para o usuário, 1536×1872, nove linhas. Manifesto original previa onze linhas; as dezesseis direções do olhar ainda não existem na imagem. Fallback procedural permanece para recurso ausente.

## Próximas etapas obrigatórias

- Expandir a fila de estudos para objetivos de pesquisa, busca de fontes, síntese verificável e critérios de qualidade. Ingestão de texto não demonstra aprendizagem de pesos; páginas continuam sendo dados não confiáveis.
- Diagnóstico por eventos e verificações específicas, evitando monitoramento de tela contínuo caro; consertos devem exigir pós-condições verificáveis.
- Ambiente isolado real para candidatos de código, benchmark de regressão independente, promoção atômica e reversão de habilidade.
- Visão e controle de tela em ciclo fechado com verificação entre ações; medir latência/precisão por aplicativo antes de anunciar capacidades.
- Coordenar STT, visão e modelos de linguagem no orçamento global; medir sessões prolongadas e concorrência real.
- Completar pet, efeitos ligados a eventos, prévias de artefatos e voz expressiva com testes de áudio reais.

## Referências de projeto

- Concorrência e consumo de contexto: https://docs.ollama.com/faq#how-does-ollama-handle-concurrent-requests
- Persistência de dados sensíveis no histórico Git: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
