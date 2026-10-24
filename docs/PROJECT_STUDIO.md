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
