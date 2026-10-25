# Inspeção de pacotes SKILL.md

Entrega de 25/10/2026: parser, captura/exportação e inventário persistente de pacotes
locais. Não ativa nem executa habilidades. O catálogo `skills` do runtime continua consultando
o formato JSON legado; a integração de pacotes depende de ativação e permissões.

Comando de inspeção, na raiz da Nyx:

```powershell
.\.venv\Scripts\python.exe tools/inspect_skill_package.py 'C:\pasta-autorizada\minha-skill'
.\.venv\Scripts\python.exe tools/inspect_skill_package.py 'C:\pasta-autorizada\minha-skill' --export 'C:\destino\pacote-novo.zip'
```

O resultado JSON mostra metadados, arquivos, exclusões, bytes e SHA-256 do snapshot.
`valid_structure` comprova somente validação estrutural. `execution_authorized`
e `functional_tests_run` permanecem falsos. Não lê arquivos referenciados fora
do pacote nem importa módulos dos diretórios scripts/references/assets.

## Formato e limites

Implementa frontmatter YAML + corpo Markdown conforme a
[especificação Agent Skills](https://agentskills.io/specification): nome obrigatório
igual à pasta, descrição e campos opcionais license, compatibility, metadata e
allowed-tools. O corpo e os recursos são preservados como dados. allowed-tools
é apenas uma declaração do autor; não amplia permissões. Versão em metadata é
preservada como texto, ainda sem resolver dependências ou versões instaladas.

Restrições locais adicionais: nomes ASCII minúsculos, números e hífens; sem hífens
consecutivos ou nas pontas. Campos desconhecidos são recusados; extensões devem
usar metadata. O parser aceita UTF-8/BOM e descrições multilinha. Não promete
aceitar todas as extensões YAML ou de outros clientes Agent Skills.

- SKILL.md: até 64 KiB; frontmatter: até 8 KiB.
- YAML: até 256 nós e profundidade 8; aliases, chaves duplicadas e tags Python
  são recusados. Usa subclasse limitada de `yaml.SafeLoader`, PyYAML 6.0.3
  explicitado nas dependências. Ver [documentação PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation).
- Pacote: até 64 arquivos, 4 MiB no total, 256 KiB por arquivo, profundidade 8.
- Captura Windows local usa a proteção nativa de `ProjectSnapshot` contra links,
  reparses e caminhos especiais. Filtros de nomes sensíveis/dependências são
  aplicados e as exclusões aparecem no relatório; não são detector universal de segredos.
- Leitura de recurso textual: caminho relativo validado, UTF-8, até 16 KiB.

Captura mantém bytes imutáveis e manifesto de hashes. O hash não autentica autor
ou procedência. A leitura de texto ocorre sob demanda sobre o snapshot; a captura
inicial ainda lê todos os arquivos incluídos, não é importação progressiva do disco.

Exportação cria ZIP novo com uma pasta raiz correspondente ao nome da skill.
Não sobrescreve ZIP existente, não extrai arquivos e não inclui entradas filtradas.
Assim, um pacote exportado pode não ter dependências excluídas: essa condição é
informada e não deve ser apresentada como pacote funcionalmente testado.

## Evidência e pendências

Testes exercitam metadados, Unicode, descrições multilinha, nomes, limites,
aliases, duplicação de chaves, tags indevidas e profundidade. Captura/exportação
real no Windows confere bytes do ZIP e ausência do efeito de um script de fixture.
Teste do comando usa processo separado e verifica que nenhum pacote foi ativado.

Regressão: **700 aprovados, 1 pulado em 64,72 s**, com navegador/Windows/LPAC
habilitados, em `build/sandbox-probes/skill-package-regression.xml`. Após ajustes
de Unicode e caminho da pasta atual, **22 testes focados aprovados**, Ruff limpo.

Ainda faltam interface, ativação após avaliação independente, permissões específicas,
execução isolada de scripts e importação ZIP. Nenhum pacote externo foi baixado
ou instalado durante esta entrega; PyYAML 6.0.3 já estava no ambiente.

## Inventário persistente de pacotes inativos

`SkillPackageStore` guarda snapshots e origem declarada em transação SQLite única.
Importar novamente o mesmo nome cria uma nova revisão local imutável, independente
da versão textual informada pelo autor em metadata. A primeira revisão começa
em 1; importar nunca substitui uma revisão anterior. Todas ficam **inativas** e
com validação **somente estrutural**. Não existe método de ativação nessa API.

O inventário padrão fica em `data/skill_packages`, protegido por ACL usuário/SYSTEM,
ignorado pelo Git e identificado por marcador próprio. Reutiliza o armazenamento
de snapshots do Estúdio em diretório separado; recusa abrir catálogo de projetos
com marcador diferente. Limites: 64 pacotes, 32 revisões por pacote, 4 MiB por
revisão e 64 MiB de conteúdo total. O SQLite mantém o teto físico de 192 MiB do
armazenador; journal transitório pode ocupar espaço adicional. Não é quota de
disco para código em execução.

Listar lê somente metadados, sem carregar blobs de recursos. Inspecionar/exportar
carrega a revisão solicitada, verifica o manifesto de hashes e reconstrói o pacote
validado. Origem é uma declaração local de até 2.048 caracteres; não autentica
autor, assinatura ou servidor. Importação de pasta registra seu caminho absoluto.
Não consulta rede, instala dependências ou reabre a origem ao ler versões salvas.

```powershell
.\.venv\Scripts\python.exe tools/manage_skill_packages.py import 'C:\pasta-autorizada\minha-skill'
.\.venv\Scripts\python.exe tools/manage_skill_packages.py list
.\.venv\Scripts\python.exe tools/manage_skill_packages.py versions minha-skill
.\.venv\Scripts\python.exe tools/manage_skill_packages.py inspect minha-skill --version 1
.\.venv\Scripts\python.exe tools/manage_skill_packages.py export minha-skill 1 'C:\destino\revisao-1.zip'
```

Use `--store 'C:\catalogo-proprio'` antes do subcomando para outro inventário vazio
ou previamente identificado. Não aponte para diretório de dados de outro aplicativo.
Cada saída repete `execution_authorized: false`. Inspeção mostra instruções como
dados; exportação exige ZIP novo. Não há remoção automática de fontes ou revisões.

Testes conferem reabertura, histórico/origens, metadados divergentes, rollback da
transação por quota, números distintos em importações concorrentes e recusa de
conteúdo adulterado. Comandos import/list/versions/inspect/export foram exercitados
em processos separados com arquivos temporários próprios, mantendo fonte intacta.

O inventário ainda não entra no BackupVault criptografado. ZIP exporta uma revisão,
não o histórico e suas origens. Pacotes inativos não ficam disponíveis como
instruções ao planejador por esse armazenamento; a integração de revisão/ativação
e permissões será uma etapa própria.

Regressão do inventário: **707 aprovados, 1 pulado em 55,12 s**; Ruff aprovado,
em `build/sandbox-probes/package-store-regression-after.xml`. A primeira tentativa
teve 1 falha/706 aprovados/1 pulado: a fixture Windows regravava seu JSON de estado
sem substituição atômica, permitindo leitura vazia durante um clique. Corrigida
a fixture, 24 testes focados e a regressão passaram. O relatório anterior foi
preservado em `build/sandbox-probes/package-store-regression.xml`.
