# Histórico de habilidades — primeira correção da fase F

Estado em 24/10/2026: `SkillManager` armazena procedimentos JSON declarativos.
Ainda não está conectado ao runtime; não executa, valida funcionalmente ou
autoriza scripts. O nome legado `promote_task_to_skill` não comprova que uma
tarefa passou em testes. O suporte a pacotes Agent Skills/SKILL.md, catálogo
na interface e permissões por habilidade continuam pendentes.

## Histórico preservado

Versões são criadas exclusivamente, sem sobrescrever arquivos existentes.
A numeração considera todo o histórico, incluindo versões não ativadas por
falha de gravação. Depois de v2 → rollback v1, uma nova promoção cria v3.
Objetos recebidos e retornados são copiados: alterar uma lista de etapas fora
do gerenciador não altera o estado registrado.

Cada versão nova registra o antecessor ativo. Restaurar retorna a esse antecessor,
não simplesmente ao número anterior; assim, uma versão órfã nunca é ativada por
essa regra. Arquivos legados, sem esse campo, conservam o comportamento numérico
anterior. Essa compatibilidade não certifica a estabilidade das versões antigas.

`current.json` é substituído atomicamente após escrever e sincronizar um arquivo
temporário. Falha antes da substituição preserva o ponteiro anterior. Se a nova
versão já foi gravada, ela permanece como registro órfão e seu número não será
reutilizado. Uma queda abrupta pode deixar um arquivo temporário para inspeção;
não há coleta automática desses arquivos nesta entrega. Não há garantia de
durabilidade absoluta contra falha de hardware/energia.

Um lock do sistema operacional serializa operações entre instâncias/processos;
concorrência ocupada retorna erro, sem espera ilimitada. Cada operação recarrega
o estado persistido, evitando cache antigo sobrescrever contadores ou versões.

## Limites e validação

- Nomes ASCII de até 64 caracteres, sem caminhos, nomes reservados do Windows ou
  colisões por capitalização. Nomes inválidos são recusados, não normalizados.
- Até 64 habilidades criadas pelo gerenciador, 32 versões por habilidade,
  12 etapas por versão, descrição de 4.000 caracteres e JSON de 128 KiB.
- Enumeração limitada a 128 entradas na raiz e 64 na pasta ao promover.
- Recusa links/reparses e hardlinks nas verificações de caminhos. Não é uma
  fronteira contra outro processo host autorizado modificando caminhos ao mesmo
  tempo; nenhuma pasta é concedida a código candidato por esse gerenciador.
- Identidade e conteúdo ativo conferidos contra a versão arquivada. Divergências
  são recusadas e registradas no log. Isso não é assinatura de origem: modificar
  ambas as cópias de forma consistente não será detectado como falsificação.

Os contadores existentes ainda descrevem a versão ativa e são informados pelo
chamador. Não constituem trilha completa de execuções. Duas falhas informadas
podem acionar rollback; isso não prova que o antecessor seja seguro ou estável.
Nenhum procedimento é executado automaticamente por essas operações.

## Evidência e próximas integrações

Testes cobrem promoção após rollback, preservação dos bytes históricos, cópias
independentes, múltiplas instâncias, lock entre processos reais, falha simulada
na substituição atômica, caminhos inválidos, hardlink, adulteração do ponteiro,
limites e compatibilidade com arquivos antigos.

Regressão: **673 aprovados, 1 pulado em 50,40 s**, com navegador/Windows/LPAC
habilitados, em `build/sandbox-probes/skill-history-regression.xml`. Depois do
ajuste de antecessor e compatibilidade, **20 testes focados aprovados** e Ruff limpo.

Ainda faltam origem/integridade autenticada dos pacotes, versões/dependências
de SKILL.md, validação antes da ativação, permissões específicas, execução pelo
runtime, estatísticas por execução, catálogo pesquisável e importação/exportação.
Não habilitar scripts com base apenas no sucesso dos testes de armazenamento.
