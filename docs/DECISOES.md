# DECISOES — registro de decisões reversíveis (uma entrada por decisão)

## D-010 · Faixa fria observada e degradação explícita · 02/11/2026

Contexto: usuário exige Normal padrão condicional e medição antes de manter piso
RAM2,5GiB. Três cargas4B/8K reais passaram partindo5,21–5,26GiB livres; não foi
medido limite físico inferior. Opções: manter palpite, criar pressão artificial
de RAM ou usar faixa observada conservadora. Escolha: faixa operacional5,3GiB
arredondada para cima na admissão fria; Normal automático quando permite, senão
Conservador. Modelo menor instalado pode substituir principal com aviso visível,
sem mudar a preferência ou baixar pesos. Residentes exatos têm regra separada.
Motivo: evita afirmar mínimo não medido e não força paginação com disco C cheio.
Pode recusar cargas viáveis abaixo dessa faixa; medir depois sob condições reais.
Reversão: commits/perfis; não altera sistema, credenciais, backups ou preferências
manuais. Evidência: evidence/runtime_hud_integration_2026-11-02.md.

## D-011 · Classificação semântica e prova do app solicitado · 02/11/2026

Contexto: regex só atendia saudações; modelo3B confundiu abrir Calculadora com
executar cálculo,0/3no HUD real. Escolha: classificador local conversa×tarefa
com histórico; conversa livre/streaming sem ferramentas. Incerteza vira tarefa
com aviso, não permissão. Pedidos exatos de abrir app restringem catálogo a UI,
mantendo modelo, confirmação e verificador; conclusão exige observação do alvo.
Motivo:72/72classificações na amostra e abertura nova real1/1, outras2bloqueadas
por reset. Não declarar qualidade factual universal: respostas preservam erros.
Reversão: commits de roteador/grounding; nunca restaurar sucesso sem pós-condição.

## D-009 · Prioridades e aceite separados por ambiente · 02/11/2026

Contexto: usuário revisou nyx-2 e determinou avanço apesar de limites ambientais.
Escolha: M0/M1 ficam parciais por foco/RAM/reset; M7 e M3 iniciados em worktrees
isoladas, integração em nyx-2 e push a cada marco/~4h. Abertura é prova de janela
nova visível/identificada/sem cloak; foco tem indicador e aviso próprios. Apps
ausentes saem do denominador com inventário explícito; processo pré-existente
não é encerrado, bench pede fechar antes. Código só fecha processos próprios
com PID/criação e origem comprovados. Normal condicional, medição fria e
classificador conversa×tarefa entram na sequência, sem regex de saudações.
Motivo: instrução expressa, evita transformar limitações do PC em paralisação.
Reversão: mudanças por commits; métricas anteriores permanecem históricas e não
são recalculadas como aprovação. Não altera pet, permissões R2/R3 ou backups.

## D-008 · Publicação sanitizada com histórico preservado · 01/11/2026

Contexto: usuário pediu envio imediato do progresso; branch nyx-2 ainda não
existe no remoto. Auditoria encontrou caminhos locais em versões intermediárias
de HANDOFF_DSH.md, STATUS.md e SPEC_CAPACIDADES.md não publicadas. Escolha:
sanitizar apenas esses documentos na cadeia local, conservar uma referência
local privada da cadeia original, preservar mensagens/autores e todos os estados
de código, publicar só nyx-2 explicitamente sem force. Motivo: histórico completo
do trabalho preservado sem introduzir esses caminhos no GitHub. Não altera main,
branch de backups, chaves, snapshots ou histórico que já estava remoto. Reversão:
referência local preservada e mapeamento de SHAs em build/diagnostic; árvore final
de código igual, sem reset destrutivo de arquivos.

## D-007 · Janela e foco no encerramento · 01/11/2026

Contexto: nove aberturas observavam janela, mas seis não tinham foco; UWP cloaked
e mudança de foreground durante resposta produziram falha real. Escolha: filtro
DWM, foco de janela existente e reconsulta R0 no fim quando a última ação é
abertura nativa. Sem refocar/reabrir silenciosamente; saída honesta se divergir.
Verificador independente aperta também identidade dos filhos UWP. Motivo:
3/9com foco no baseline→9/9em dois ensaios posteriores; falha intermediária
preservada. Reversão: commits de código reversíveis, mas não restaurar afirmações
de sucesso sem observação. Spotify/WhatsApp preferem nativo; web só NOT_FOUND.

## D-006 · Scanner offline isolado e serial · 01/11/2026

Contexto: CI não colecionava sem Qt e não havia barreira de segredos no commit.
Escolha: requisitos CPU/testes GUI opcionais e detect-secrets/pre-commit isolados
no volume do projeto; todos os plugins, baseline auditado por candidato,
verificação de credenciais na rede desativada. Scan serial limita concorrência
de memória. Medição de startup até0,779s/~55MiB RSS por CLI. Reversão: reverter
arquivos/configuração e retirar somente o hook local instalado nesta sessão;
não remover dados do usuário nem alterar backups/credenciais.

Formato: `## D-NNN · título · data` → Contexto · Opções · Escolha · Motivo (com dado medido) · Como reverter.

## D-001 · Adotar o pacote sem reiniciar o trabalho · 01/11/2026

Contexto: pacote novo descreve M0–M8; já existem correções/evidências em commits.
Opções: substituir o projeto, reiniciar de main ou criar branch a partir do estado
atual. Escolha: `nyx-2` derivada de `5fc8ee5`, arquivos do ZIP somente onde não
existiam. Motivo: preservar 913 passes e os resultados/falhas reais, sem presumir
que isso conclui os novos gates. Reversão: branch anterior continua disponível;
novos documentos podem ser revertidos por commit, sem apagar dados locais.

## D-002 · Mínimos da bateria e evidência herdada · 01/11/2026

Contexto: cabeçalho pede40 tarefas; categorias enumeram50. Escolha: manifesto50,
três execuções e verificadores independentes. Testes antigos e adapters diretos
continuam evidência diagnóstica, sem promovê-los a aceite completo do planejador.
Motivo: não reduzir cobertura/afrouxar gate. Reversão: alteração explícita da
especificação pelo usuário; métricas antigas permanecem identificadas.

## D-003 · Suspender envios públicos após aprovação · 01/11/2026

Contexto: GitHub confirmou público e branch de backup existente. Proposta em
PROPOSTA_BACKUPS.md aprovada explicitamente pelo usuário. Escolha: suspender
uploads no código e desativar a preferência nos INIs de fonte/instalação;
preservar timer local, backups, chave e branch remota. Motivo: autorização cobre
suspensão de novos envios, sem migração/remoção. Reversão: requer decisão futura
e destino privado verificado; nenhuma opção de UI contorna a suspensão atual.
Instâncias antigas já abertas não foram reiniciadas ou atualizadas à força.

## D-004 · Aprovação de ensaio só no diálogo de produção · 01/11/2026

Contexto: adapters isolados não exercitam a experiência completa. Escolha:
DesktopWindow/OverlayWindow temporários, modelo real, QTest clicando o botão
do PermissionDialog real e observação Win32 em módulo independente. Motivo:
9/9aberturas de três apps observadas, com uma confirmação cada. Guardas negam
outras ações; não se liga Autônoma nem se opera a Nyx pessoal. Reversão: remover
o harness/rota de bench, sem modificar comportamento ou dados do produto.

## D-005 · Não fechar apps pessoais para melhorar o gate · 01/11/2026

Contexto: repetições observaram apps já abertos; fechamento poderia afetar o
uso do PC. Escolha: preservar os apps e marcar gate_eligible=false, mostrando
already_visible_before e cobertura faltante. Motivo: nove passes parciais não
são o gate de15apps com reset. Reversão: acrescentar depois cleanup de fixtures
cuja propriedade e segurança possam ser comprovadas, mantendo confirmações R3.
