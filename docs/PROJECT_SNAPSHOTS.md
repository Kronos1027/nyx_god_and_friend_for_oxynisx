# Projetos: cópia limitada e exportação no Windows

Estado em 24/10/2026: componente funcional, ainda não conectado à interface de
criação ou ao executor padrão do CodeTask. Não constitui quota de disco para um
processo em execução. O backend de arquivos suporta somente Windows local.

`ProjectSnapshot.capture` lê arquivos sem importar ou executar código do projeto.
Produz um inventário imutável de bytes e um manifesto com caminhos, tamanhos e
SHA-256 por arquivo e do conjunto. O manifesto também informa entradas excluídas.
A cópia representa os arquivos efetivamente lidos; não promete um instante único
e atômico para um repositório inteiro que esteja sendo editado simultaneamente.

Limites padrão: 512 arquivos, 4.096 entradas visitadas, 16 MiB no conjunto, 4 MiB
por arquivo, 16 níveis de diretórios e prazo cooperativo de 10 segundos. Valores
maiores são limitados pelo construtor; não há configuração ilimitada. Cancelamento
e prazo são checados entre operações de I/O; um erro/bloqueio do disco depende
também do retorno da chamada do sistema operacional.

Não copia `.git`, ambientes virtuais, `node_modules`, caches ou nomes comuns de
credenciais (`.env*`, `.pem`, `.pfx`, `.key`, entre outros). Isso não é um detector
de todos os segredos possíveis. Pastas vazias não são representadas. Dependências
excluídas não são reinstaladas automaticamente; ausências precisam ser reportadas
ao preparar a execução.

## Proteção de caminhos e evidência adversarial

- Só aceita volumes locais; recusa UNC, dispositivos, ADS, componentes `..`, nomes
  reservados, caracteres de controle, colisões de capitalização e caminhos conflitantes.
  Uma unidade de rede mapeada por letra também é recusada pelo tipo do volume.
- Recusa hardlinks, reparse points, arquivos especiais e arquivos offline.
- Usa `NtCreateFile` com `OBJ_DONT_REPARSE`, fazendo o Windows recusar reparses
  durante a resolução de todo o caminho, inclusive ao criar arquivos/diretórios.
- Enumera usando `NtQueryDirectoryFile` sobre o handle aberto; não reabre o caminho
  para listar conteúdo. Ancestors permanecem abertos durante a cópia.
- Handles de arquivo não permitem compartilhamento de escrita/exclusão enquanto
  os bytes são lidos e conferidos.

O primeiro teste de ataque mostrou que checar atributos e manter um diretório
aberto era insuficiente: ele podia virar uma junction no lugar. O teste atual
repete a conversão com acesso somente a atributos, mesmo com o diretório aberto.
A enumeração continua no objeto original e as tentativas de ler/criar arquivos ou
subdiretórios pelo redirecionamento são recusadas; o alvo externo permanece intacto.
Os testes usam somente diretórios e sentinelas temporários próprios.

## Materialização e exportação

`write_new_directory` cria uma árvore nova a partir dos bytes capturados. Nunca
reutiliza ou sobrescreve um destino existente. O chamador deve controlar a pasta
pai e conceder acesso ao candidato somente depois de preparar a cópia. Em caso
de falha, a árvore nova parcial é preservada para inspeção; não há remoção recursiva
automática nem recuperação de staging integrada ainda.

`export_zip` grava um arquivo novo contendo apenas os arquivos imutáveis capturados,
com nomes relativos validados, sem links e sem extração. Não sobrescreve ZIPs
existentes. O snapshot de resultados deve ser capturado depois que o executor
confirmou o fim de todos os processos. O ciclo de vida será imposto pelo futuro
gerenciador de projetos, não por código candidato.

## Ensaio real de projeto com múltiplos arquivos

`test_multifile_project_copy_test_fix_and_export_inside_lpac` cria `ops.py` e
`test_ops.py`. A primeira versão calcula incorretamente 28 − 68 e falha no teste
executado dentro do LPAC. A fixture fornece uma correção conhecida para somar;
uma segunda cópia passa no mesmo teste isolado. O resultado é capturado após o
encerramento do Job, exportado e comparado por conteúdo e hashes.

Esse ensaio prova cópia → execução isolada → falha → correção roteirizada → teste
aprovado → exportação. Não prova geração/correção autônoma pelo modelo nem o fluxo
da interface Creation Studio. A suíte contém 29 testes de snapshots/arquivos e
15 do LPAC, incluindo o novo fluxo. A regressão completa, com navegador/Windows/LPAC
reais, terminou com **606 aprovados, 1 pulado em 51,39 s**; Ruff aprovado.
Relatório local: `build/sandbox-probes/project-regression.xml`. Entre os testes
adicionais está a ausência de vazamento de handles após vinte falhas provocadas
na conversão do handle nativo para descritor Python.

Ainda faltam gerência persistente de projetos/versões, recuperação de pastas
parciais, quota de escrita durante execução, integração com permissões/recursos,
apresentação de prévias e avaliação do fluxo com o modelo escolhido.

Fontes primárias: [OBJECT_ATTRIBUTES e OBJ_DONT_REPARSE](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes),
[criação nativa de arquivos](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/nf-wdm-zwcreatefile),
[compartilhamento de handles](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
