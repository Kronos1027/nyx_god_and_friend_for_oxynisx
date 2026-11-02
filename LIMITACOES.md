# LIMITACOES.md — limitações reais, sem contorno silencioso

## Atualização de 01/11/2026

- Gate ampliado permanece reprovado:7/36tentativas nativas executadas antes de
  pressão de RAM, apenas2concluídas nessa rodada;29bloqueadas no runtime e9sem
  rota no total45. Não inferir sucesso ou incapacidade universal das demais.
  Foco negado em apps instalados continua sem causa confirmada. Consultas de
  integridade/job não mostraram restrição simples que explique todas as falhas.
- Benchmark amplia rotas, mas não oferece reset seguro de apps pessoais. Não
  fecha esses apps para liberar RAM; piso1GiB de inferência permanece ativo.

- Gerenciador de Tarefas: foco bloqueado por Windows. UIA retornou erro COM
  -2146233079; alternativa Win32 retornou `(5, BringWindowToTop, Acesso negado.)`
  em3/3. Janela existe, mas não recebe foco; tarefa não aprovada. Sem elevação ou
  redução de proteção. Demais apps continuam em verificação.

- Defeito crítico de foco corrigido no incremento: uma rodada intermediária da
  Calculadora divergiu no encerramento; revalidação final adicionada. Dois ensaios
  posteriores9/9sem divergência. Categoria/marco seguem bloqueados por cobertura.
  Isso não garante que o foco permaneça após a conclusão ou interferência humana.
- Spotify/WhatsApp nativos não encontrados neste catálogo; preferência nativa
  testada unitariamente. Login/mídia real continuam adiados. Perfil Conservador
  pode recusar4B com pouca RAM mesmo com VRAM livre; não foi afrouxado.

- Regressão completa após higiene encontrou seis falhas de foco;12casos isolados
  posteriores passaram. Isso não elimina a instabilidade e não fecha gate.
- CI mínimo validado no Windows sem Qt; Ubuntu remoto não executado. Scanner
  offline cobre working tree/arquivos do commit, não todo histórico/refs/backups.

- Runner M0 cobre seis dos50casos;44cenários seguros ainda pendentes.
  Um PASS antigo de arquivos omitiu calculator; foi reavaliado como método
  incompleto. Checker/guarda apertados;3/3 posteriores cumpriram o método.
  Conferência de total por texto e ledger não é auditoria universal ou de syscall.
- Calculadora/Bloco de notas/Paint passaram pela UI real e verificador Win32,
  mas os aplicativos não são fechados/resetados entre rodadas. Gate Apps segue
  inelegível; não testadas as outras12entradas, funcionalidades internas, login,
  DPI distintos ou a distribuição congelada. Nenhum app pessoal foi encerrado.
- Retomada automática da bateria somente para rotas de leitura/conversa.
  Relatório legado sem fingerprint é marcado como diagnóstico; não promove marco.
  Escrita atômica pode falhar se o Windows mantiver o arquivo ocupado além das
  dez tentativas; conserva relatório anterior e temporário, sem alegar conclusão.

- Envios de backups ao GitHub foram suspensos após aprovação explícita; cópias
  locais/chave preservadas e branch remota não apagada. Preferências locais
  desativadas. Código antigo já carregado ou executável instalado anterior à
  correção não foi substituído/reiniciado: não há garantia de bloqueio nesse
  processo até usar a versão atualizada. Não auditado todo o histórico público.
- Plano M0–M8 adotado na branch nyx-2. Os números anteriores são evidências
  parciais; não substituem bateria independente50tarefas/3execuções ou soak2h.

## Estado atual — núcleo de desktop (31/10/2026)

- Diagnóstico sob demanda lista grupos por nome e working set com consulta
  explícita. Memória compartilhada pode ser contada duas vezes; não representa
  liberação garantida. Limite cooperativo de 1 s pode produzir lista parcial.
  A medição não fecha programas, libera RAM ou habilita observação contínua.

- Primeiro trecho de saudações simples foi medido em 0,125–0,281 s com Qwen4
  aquecido; cartão Qt isolado em 0,219 s. Não comprova voz ou conversa geral.
  Roteador em fluxo é deliberadamente estreito: saudações e identidade exata,
  somente Ollama. Identidade é retida para conferência de padrões conhecidos
  após uma alegação falsa real; outras formulações ainda podem escapar.
  Cancelamento é cooperativo e leitura HTTP pode esperar timeout. Não há TTS
  por frase, tool calling nativo ou fluxo llama.cpp nessa mudança.

- Atualização após liberação de RAM: o ensaio real de arquivos e a escolha Steam
  passaram. Perfis manuais adicionados; padrão Conservador preservado. Normal/Foco
  foram medidos em contexto 8K/16K, sem forçar flash attention ou cache q8_0.
  Automação de perfil por jogo/OBS, limites globais de toda a Nyx e latência de
  voz ainda não foi validada. Reservas de KV são estimativas.
- A conferência de soma cobre pedidos estreitos de arquivos numéricos: operandos,
  subtotal duplicado, total declarado e intervalo explícito de nomes simples.
  Não é verificador universal. Texto por extenso, operações compostas, caminhos
  equivalentes absoluto/relativo e intervalos ambíguos ainda têm limites.
  Seis tarefas reais finais passaram; isso não conclui o gate de tarefas variadas.

- Descoberta agora inclui aliases, pastas fixas, atalhos do Menu Iniciar sem
  argumentos e UWP registrado. Atalhos com argumentos arbitrários e portáteis
  continuam sem suporte geral; fuzzy retorna candidatos, não escolhe por conta.
  Chrome/VS Code não encontrados neste ensaio. Resultados de Spotify/WhatsApp são
  navegação web, sem login ou prova de reprodução.
- Breaker transitório separa operação/alvo e tem cooldown; não garante que uma
  nova tentativa será correta. A UI mantém ferramentas administrativamente
  desativadas e parada de emergência. Reset por nova tarefa está no TaskRunner;
  a CLI de uma ação ainda exige reset explícito se não esperar cooldown.
- O gate de aceitação completo ainda não foi atingido. Evidências iniciais usam
  verificador de produção; faltam verificadores independentes, 40+ tarefas, picos
  e sessões prolongadas. Traces locais podem conter pedidos/resultados privados;
  não devem ser publicados. A captura ainda não inclui prompt/ToolResult completos.
- Histórico anterior à liberação de RAM: inferência não passou, serviço indisponível inicialmente,
  depois recusa de orçamento. A sondagem final encontrou menos de 1 GiB RAM livre
  e orçamento de pesos zero, com mais de 10 GiB VRAM livres. Erros agora informam
  tamanho/orçamento/recursos e distinguem inventário ausente. Reservas preservadas.
- JSONs de runtime foram removidos do índice e ignorados, preservando os locais.
  Isso não remove cópias do histórico público; varredura completa de segredos e
  políticas CI/pre-commit permanecem pendentes.
- Política de observação R0 está conectada ao desktop, com allowlist estrita.
  Parceira, aprovação por plano e allowlists persistentes não estão implementadas;
  ações de entrada e abertura continuam confirmadas conforme o modo existente.

O ambiente atual é Windows com RTX 3060. As seções L1–L4 abaixo são histórico
do desenvolvimento inicial, não descrevem a máquina atual.

- O orçamento de prompt estima tokens por bytes; não é uma contagem exata do
  tokenizer. Compacta detalhes opcionais sem cortar pedido atual e estados das
  etapas. Se o mínimo não cabe, a tarefa pausa. O ensaio real passou com oito
  leituras e cálculo, mas isso não garante planejamento correto para toda tarefa.
- Cálculo decimal é limitado e informa arredondamento. O modelo ainda precisa
  selecionar os operandos corretos; schema válido não prova semântica correta.
- A biblioteca Steam local é consultável por manifests. Pode incluir utilitários
  e não comprova licença ou execução. A escolha pelo modelo ainda não foi
  validada nesta revisão: a reserva de RAM bloqueou o ensaio.
- Checkpoints antigos sem conversa vinculada não são retomados pela interface
  em outro chat; revise as etapas e formule um novo pedido. Novas tarefas
  preservam o vínculo. Ver `docs/RELIABILITY_2026-10-30.md`.

- A continuação de tarefas na interface é automática em blocos de seis quando
  as seis últimas ações foram bem-sucedidas e verificadas, até 48 ações/30 minutos.
  Essa regra remove a parada fixa em seis; não comprova progresso semântico nem
  garante conclusão de qualquer pedido. Repetições, falhas e limites globais ainda
  podem interromper uma tarefa. Ver `docs/TASK_EXECUTION.md`.
- A descoberta não é universal. Identidade de executável, UWP ou instalação
  específica precisa ser observada; abrir processo sem janela não basta.

- O cliente Ollama agora regenera uma vez uma saída JSON inválida/interrompida,
  sem executar a proposta descartada. Isso não garante recuperação de toda falha:
  orçamento, cancelamento, pressão de memória ou nova saída inválida encerram
  a tentativa. JSON válido também não comprova que a ação escolhida é correta.
  O cancelamento de uma chamada HTTP já enviada aguarda seu retorno/timeout.
  Ver `docs/JSON_RECOVERY.md`.

- A Central organiza as capacidades existentes; não ativa servidores MCP nem
  executa scripts gerados. Sua prévia visual é feita com modelo de demonstração;
  esse rótulo não representa troca do modelo configurado no aplicativo real.
  O resumo de tarefas é consultado ao entrar na Central; a telemetria do sistema
  e o estado da sessão são atualizados periodicamente enquanto a janela está aberta.
  A revisão de interfaces é incremental, não encerra o roteiro Evolution 2.0.

- MCP não está conectado ao runtime/UI. O cliente já conversa com servidor de
  ensaio dentro do LPAC, com deadline/cancelamento reais e política de negação
  por padrão. Faltam gerência persistente, aprovação vinculada ao servidor,
  credenciais e integração ao planejador; T9 permanece parcial. Não há transporte
  HTTP, suporte universal de versões ou lançamento alternativo no host.
  Ver `docs/MCP_STATUS.md`.

- A aba Habilidades importa, versiona, inspeciona e exporta pacotes SKILL.md,
  mas ainda não avalia nem ativa suas instruções/scripts no runtime. Origem é
  declarada, não autenticada; hash detecta alteração, não garante confiabilidade.
  A consulta de habilidades legadas no runtime permanece uma capacidade separada.

- Há um protótipo LPAC real, com ensaios de isolamento e recuperação aprovados, ainda sem
  integração ou qualificação para produção. Recuperação dos perfis após queda
  do supervisor foi validada com encerramento real dos processos. Faltam quota
  de disco, gestão/recuperação de staging, exportação e validação adversarial ampliada. Python requer
  `registryRead` no ensaio; `_ctypes` não importou. Ver
  `docs/WINDOWS_SANDBOX_PROTOTYPE.md`. CodeAct e execução de testes por
  code_task estão bloqueados; propostas textuais continuam disponíveis. A
  aprovação de uma ação não transforma subprocesso comum em sandbox.
- Cópia limitada e exportação de projetos existem e foram usadas num ensaio real
  de múltiplos arquivos no LPAC. A correção do ensaio foi roteirizada, não gerada
  pelo LLM. O catálogo do Estúdio usa snapshots para importar/versionar/exportar,
  mas não executa projetos. O botão legado de execução no host foi bloqueado.
  Banco de projetos protegido por ACL não está criptografado nem incluído no
  BackupVault; exportação ZIP contém somente uma versão. Snapshots suportam
  Windows local, recusam links e dependências/nomes sensíveis conhecidos, mas não
  detectam todo segredo e não preservam diretórios vazios. Falha ao materializar
  preserva a nova árvore parcial; recuperação dessas pastas ainda falta.
- Testes automatizados de rollback usam executor roteirizado. O teste adversarial
  do executor padrão comprova que ele não inicia código. Ensaios LPAC separados
  comprovam somente os recursos proibidos explicitamente testados.
- Diagnóstico inicial Qwen3.5 4B falhou por admissão de memória após uma leitura;
  após a fase B passou com duas leituras reais e soma conferida. Evidência:
  build/evolution-baseline/task-after-b.json. Não é comparação de velocidade.
- Spotify abriu no Edge isolado e mostrou “Entrar”; reprodução autenticada
  depende de login humano. Não foram importadas credenciais ou cookies.
- O usuário adiou o login; trabalho independente continua. UIA foi validada
  contra aplicação Windows própria, em conjunto com Qt, em escala da aplicação
  1,0/1,5. Não prova múltiplos monitores, DPI do sistema diferente, jogos ou OCR.
  O auxiliar UIA separado resolve conflito observado no processo com Qt, mas
  ainda falta distribuí-lo no pacote congelado. Execução pelo fonte disponível.
- Localizadores atuais cobrem DOM comum; frames, shadow DOM e acessibilidade
  completa não são suportados. Mídia inacessível retorna incerteza. Perfil
  separado protege dados entre sessões, mas não é sandbox de código gerado.
- Spotify com login, microfone real, sessão prolongada e novas fases A–J ainda
  exigem evidência específica. Ver docs/EVOLUTION_2_BASELINE.md.
- Tarefas persistentes estão conectadas ao desktop. Retomada exige ação humana;
  efeitos externos incertos bloqueiam continuação e exigem inspeção/novo pedido.
  Dependências existem para equipes de consulta; ainda falta plano geral com
  dependências de escrita, reconciliação guiada e verificação semântica do objetivo.
  Testes de recuperação usam planejamento roteirizado com arquivos reais.
  Um ensaio de três microagentes dependentes passou com Qwen real; não comprova
  ganho de desempenho. Cancelamento bloqueia ações tardias, mas chamadas nativas
  ou HTTP já em curso dependem de seus próprios timeouts; não mata threads.

> Regra do prompt mestre (seção 1): bloqueio real vai pra cá com o erro
> exato, depois de ~2 tentativas de abordagens diferentes. Nada de solução
> fake pra "seguir em frente".

## L1 — Ambiente de desenvolvimento não é o Windows alvo (estrutural)

O desenvolvimento inicial está acontecendo em um ambiente **Linux** sem GPU
NVIDIA, sem PowerShell e sem as libs exclusivas de Windows
(`pywinauto`, `PyQt6` overlay, `faster-whisper` com áudio real). Consequência
honesta:

- Tudo que é multiplataforma (allowlist, sandbox, GBNF/validação, auditoria,
  loop, macros) é **testado de verdade** — 111 testes + CI Linux.
- O que SÓ existe no Windows alvo está **pendente de validação real** e
  marcado como tal no STATUS.md:
  - comportamento do Qwen2.5-7B real com a gramática GBNF (os 20 prompts da
    Fase 1);
  - execução do dialeto powershell dos templates;
  - overlay PyQt6 renderizado (Fase 2) e sua captura de tela;
  - transcrição real do faster-whisper (Fase 3);
  - automação pywinauto (Fase 4);
  - leitura de VRAM/RAM (Fase 6).

Não é um bloqueio de código — é um limite de ambiente, tratado com
honestidade em vez de testes fingidos.

## L2 — Validação dos 20 prompts contra o modelo real: PENDENTE

A definition of done da Fase 1 pede "20 prompts variados, 0 falhas de parse"
com o modelo real. O que existe hoje:

- gramática `schema.gbnf` pronta e sanity-checkada;
- validador Python testado com 20+ payloads variados (camada 2);
- `OfflineLLM` para exercitar o ciclo SEM modelo — claramente rotulado como
  "não é o modelo real" no CLI e nos testes.

O que falta: baixar o GGUF na máquina Windows, rodar os 20 prompts com
`llama-cpp-python` + CUDA e colar o log aqui. Tentativa de contorno no
ambiente Linux (instalar llama-cpp-python CPU + modelo pequeno) foi avaliada
e descartada: validaria outro modelo, em outra máquina, com outra
quantização — prova fraca com custo alto. A prova forte é no alvo.

## L3 — pywinauto não instala em Linux (esperado)

`pip install pywinauto` falha fora do Windows (dependência de
`pywin32`/comtypes). Impacto: nenhum — `ui_tool.py` é stub da Fase 4 e o
import é lazy; o CI não toca nele.

## L4 — Confirmação por UI ainda não existe (Fase 5)

O loop devolve `needs_confirmation` + `pending_action` + o comando exato, e
o CLI faz a ponte via terminal. O `permission_dialog.py` PyQt6 (clique real
na overlay) é Fase 5 — até lá, a "UI" é o terminal. A regra de que
confirmação nunca vem de texto interpretado pelo LLM já é aplicada pelo
design do loop (`confirm_pending` é chamado pela UI, não pelo LLM).

## Itens futuros (fora do escopo inicial — não implementar sem alinhar)

- **Consciência de tela via OCR/visão** para automação de UI mais confiável
  (objetivo de médio prazo citado no prompt mestre — fica documentado aqui,
  fora do escopo inicial).
- Wake word dedicada ("Ei, Nyx") com openWakeWord/Porcupine — Fase 3 decidirá
  entre isso e trigger manual por hotkey, conforme budget de VRAM.
