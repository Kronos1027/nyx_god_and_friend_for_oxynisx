# Histórico de habilidades — primeira correção da fase F

Estado em 24/10/2026: `SkillManager` armazena procedimentos JSON declarativos.
Seu catálogo agora pode ser consultado pelo runtime; o gerenciador não executa,
valida funcionalmente ou autoriza scripts. O nome legado `promote_task_to_skill` não comprova que uma
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

## Catálogo conectado ao runtime

A ferramenta `skills` está registrada no CLI/desktop, schema JSON, gramática GBNF
e instruções do modelo. Usa o diretório legado `skills` na raiz de dados do
runtime, agora ignorado pelo Git. A criação do diretório ocorre somente na
primeira consulta. Não migra nem apaga dados existentes.

- `list`: lista nomes, descrições resumidas, versões e quantidade de etapas.
- `search`: filtra nome/descrição por todas as palavras da consulta, sem LLM.
- `get`: carrega uma versão ativa ou específica, com etapas completas, digest
  SHA-256 do procedimento e ferramentas declaradas ausentes/desabilitadas.

Listagem usa cinco itens por padrão, até vinte, com descrição limitada a 160
caracteres. Consulta aceita até 200 caracteres. Procedimento carregado deve
caber em 4.000 bytes serializados; resposta total até 6.000 caracteres. Excesso
retorna erro, sem entregar etapas parciais. O TaskRunner conserva a última
consulta completa dentro desse limite, separada do resumo truncado do histórico,
como mensagem de dados externos. Não insere procedimentos no prompt de sistema.
O digest identifica conteúdo, não certifica origem ou autorização.

Consultar não executa etapas, promove versões, faz rollback ou altera permissões.
O modelo pode propor ações correspondentes pelo fluxo normal; o registro,
confirmações, orçamento, cancelamento e verificador continuam valendo para cada
ação. Ferramentas inexistentes são informadas, não instaladas. Emergência impede
consultas também. Nenhuma execução de script foi habilitada por essa integração.

Listar retorna apenas metadados ao modelo, mas a implementação atual ainda lê
arquivos ativos para validá-los: isso não é carregamento progressivo de disco.
Faltam painel de catálogo, pacotes SKILL.md, validação/ativação explícita por skill,
dependências, permissões próprias, estatísticas por execução e importação/exportação.
A [especificação Agent Skills](https://agentskills.io/specification) foi consultada;
o formato JSON legado não é apresentado como compatível com ela.

Regressão da integração: **679 testes aprovados, 1 pulado em 49,57 s**, incluindo
navegador/Windows/LPAC habilitados; Ruff limpo. Relatório:
`build/sandbox-probes/skill-catalog-regression.xml`. Testes com planejamento
roteirizado confirmam leitura → confirmação exata → escrita real em arquivo
temporário, ausência de execução na consulta e passagem integral ao planejador.
O ensaio com modelo real é separado: `tools/verify_skill_workflow.py`.

**Qwen3.5 4B real: aprovado em 32,14 s.** O modelo encontrou o procedimento,
consultou suas etapas, propôs a escrita, aguardou confirmação, gravou a nota e
releu o código esperado. O harness só aprovou o arquivo e conteúdo temporários
previamente definidos pela fixture; essa aprovação não integra o runtime normal.
Nenhum script do procedimento foi executado. Relatório preservado:
`build/evolution-baseline/skill-attempts/576032b036494dc1865baf79fd16a801.json`.
É um caso funcional, não benchmark comparativo ou garantia de desempenho geral.
