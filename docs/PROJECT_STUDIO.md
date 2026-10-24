# Estúdio: projetos e versões

Entrega de 24/10/2026. Na janela Estúdio, a aba Projetos permite importar uma
pasta autorizada, registrar novas versões dessa pasta, visualizar arquivos,
restaurar uma versão anterior, exportar ZIP e excluir o histórico selecionado.
Na aba Código, **Guardar como projeto** registra o texto exibido. As quatro abas
anteriores continuam disponíveis. Não há execução de projetos nesta interface.

## Persistência e limites

`ProjectStore` guarda projetos, versões e bytes em SQLite, no diretório
`data/studio` da Nyx (AppData/Nyx no executável instalado). Diretório identificado
por marcador e protegido por ACL do usuário/SYSTEM. Recusa pasta existente de
outra finalidade e caminhos com links. Dados ignorados pelo Git.

- Até 64 projetos, 50 versões por projeto, 512 arquivos e 16 MiB por versão.
- Até 128 MiB de conteúdo total; SQLite limita o arquivo a 192 MiB. Arquivos
  transitórios do SQLite podem ocupar espaço adicional. Não é quota de sandbox.
- Cada versão é imutável. Restaurar v1 depois de v2 cria v3, preservando v1/v2.
- Transações impedem versões parciais e números duplicados entre escritores.
- Carga verifica tamanho, inventário e hashes antes de disponibilizar a versão.
  Corrupção bloqueia prévia/exportação; a interface descarta o conteúdo anterior.
- Exclusão afeta apenas registros do projeto selecionado. `secure_delete` do
  SQLite limpa células removidas; não promete eliminação forense em SSD/backups.

O banco não possui criptografia própria e ainda não entra no BackupVault,
cujo limite existente é menor que o catálogo. ZIP é uma cópia de uma versão,
não um backup completo do histórico. Nenhum dado é enviado a serviços externos.

## Interface e arquivos

I/O usa um worker por painel; botões de mutação ficam indisponíveis durante a
operação. Fechar durante I/O solicita cancelamento cooperativo e aguarda a
finalização antes de permitir destruir a janela. Ocultar preserva o painel.
Cancelamento da captura é checado entre chamadas de disco; não mata threads.

Prévia somente textual UTF-8, até 128.000 bytes; binários mostram metadados.
Não importa módulos, renderiza HTML ou inicia código. Importação aplica as
restrições de `PROJECT_SNAPSHOTS.md`, incluindo exclusão de dependências e nomes
comuns de credenciais. Esses filtros não detectam todos os segredos possíveis.
Exportar exige arquivo ZIP novo, sem sobrescrever existentes.

O botão legado Executar Script chamava Python no host. Esse caminho foi removido,
incluindo chamada direta ao método, e permanece indisponível. Aprovação de um
clique não substitui isolamento. A interface informa **Testes não executados**.

## Evidência

Testes exercitam reabertura do banco, integridade, quota transacional, concorrência,
restauração e exclusão seletiva; Qt real exercita importação, versão, prévia,
restauração, ZIP, falha de carga e ausência de execução do código exibido.
Fixture de I/O bloqueado confirma que um timer Qt continua disparando e que
fechar a janela não destrói o worker ativo. Não é benchmark de sessão prolongada.

Regressão completa: **616 aprovados, 1 pulado em 50,18 s**, incluindo testes reais
de navegador/Windows/LPAC, em `build/sandbox-probes/studio-regression.xml`.
Após tratar a versão corrompida na UI: **16 testes focados aprovados**, Ruff limpo.
Prévia revisada: `build/previews/studio-projects.png`.

Ainda pendem registros de execução e resultados no catálogo, integração do LPAC
com permissões/governador, quota durante execução, recuperação do staging,
geração/correção multifile pelo modelo e adaptadores de mídia opcionais.

## Ferramenta conectada à interface

`WorkspaceTool` passa código, relatório, tabela ou pedido de telemetria a um
despachante criado na thread principal durante a montagem do runtime desktop.
Widgets são atualizados por slot Qt nessa thread. O chamador só recebe sucesso
depois da exibição confirmada. Sem QApplication/conexão gráfica, retorna falha;
o CLI não anuncia uma janela inexistente. Referência: [threads e objetos Qt](https://doc.qt.io/qt-6/threads-qobject.html).

Há no máximo um pedido em voo por aplicação, compartilhado entre instâncias da
ferramenta. A espera padrão é de cinco segundos (máximo configurável de dez).
Se expirar antes do slot começar, o pedido fica descartado e não abre uma janela
posteriormente. A fila permanece ocupada até esse evento ser consumido, evitando
acúmulo durante travamento da UI. Cancelamento global/local usa o controlador do
registro; a sonda captura o cancelamento local mesmo atravessando threads.

Se a renderização já começou e a confirmação não chegou, retorna
`outcome_unknown`, que faz o TaskRunner interromper a tarefa para inspeção.
Não mata a thread da interface. Callbacks do overlay não reabrem a janela
independentemente do resultado da ferramenta.

Entradas são limitadas a 256.000 caracteres, título de 200 e linguagem de 40.
Tabelas aceitam até 1.000 linhas, 50 colunas, 10.000 células, 4.000 caracteres por
célula e 256.000 no total. CSV usa parser com suporte a campos entre aspas;
linhas mais largas não perdem células. Estruturas inválidas são recusadas antes
de tocar na interface.

Telemetria usa worker separado, um por janela. Sucesso da ferramenta confirma a
janela; o resultado de hardware permanece explicitamente pendente até a consulta
terminar. Fechar durante consulta preserva o worker. Ao sair da aplicação,
`StudioLifecycle` adia o evento Quit, solicita cancelamento da captura e mantém
o loop Qt ativo até os workers próprios terminarem. Novas exibições são recusadas
durante esse encerramento. Não impõe cancelamento forçado a I/O do sistema.

Testes Qt com thread real conferem exibição, timeout antes/depois do início,
cancelamento, limite da fila, erros de renderização, CSV e parâmetros inválidos.
Processos de fixture separados comprovam falha honesta sem interface e saída
durante worker ativo, com timer responsivo e descarte de novas exibições. Os
testes de I/O lento usam bloqueios controlados; não representam benchmark de
disco nem sessão prolongada. A consulta de hardware original também integra a
regressão; a fixture lenta não é apresentada como medição real.

Regressão desta integração: **634 aprovados, 1 pulado em 46,90 s**, com
navegador/Windows/LPAC reais habilitados; Ruff aprovado. Relatório:
`build/sandbox-probes/workspace-dispatch-regression.xml`. Não inclui novo teste
com LLM nem login no Spotify, que continua adiado por escolha do usuário.
