# Executor Windows LPAC — protótipo verificado parcialmente

Data: 24/10/2026. Não está registrado como ferramenta nem conectado ao CodeAct,
CodeTask, skills ou MCP. A execução de candidatos nesses caminhos continua
bloqueada. Este documento não qualifica o backend para produção.

## Evidência real disponível

`src/core/windows_sandbox.py` cria um perfil AppContainer novo por contexto,
inicia o processo suspenso, configura um Job Object e verifica o token antes
de liberar sua primeira thread. Não existe fallback para subprocesso comum.
O Job é associado atomicamente por `PROC_THREAD_ATTRIBUTE_JOB_LIST` na criação;
não há mais intervalo entre criar o processo e atribuí-lo ao Job. Uma queda do
supervisor nesse ponto também aciona kill-on-close.

As verificações cobrem AppContainer, SID exclusivo esperado, conjunto exato de
capabilities, mitigação Win32k e semântica LPAC: um descritor que concede acesso
apenas a ALL APPLICATION PACKAGES é recusado, enquanto o SID específico recebe
acesso. O teste positivo evita interpretar qualquer recusa como prova de LPAC.

O ensaio copia o Python instalado e a biblioteca padrão para uma pasta temporária.
Somente essa cópia recebe ACL de leitura/execução para o SID novo; a subpasta de
trabalho recebe escrita e integridade baixa. Não altera ACLs do Python instalado,
do Windows ou de arquivos pessoais. Links e reparse points são recusados antes
da aplicação recursiva de ACL. O pai passa apenas stdin vazio e o pipe de saída;
o ambiente do usuário não é herdado, salvo caminhos Windows necessários.

O Job limita memória, tempo de CPU, processos ativos e interação com a interface.
O supervisor limita tempo decorrido e saída, observa cancelamento e encerra o Job.
Antes do encerramento, reduz o limite de processos para impedir novas criações,
captura handles de membros cuja associação ao Job foi confirmada e espera esses
handles. Contagem zero de processos associados, sozinha, não provou término no
ensaio inicial. O teste detectou esse retorno antecipado e passou após a correção.

Os dez testes reais em `tests/test_windows_sandbox_live.py` verificam:

- Python calcula 28 + 68 e grava o resultado no workspace.
- Leitura/escrita de um arquivo externo de teste e alteração do runtime são negadas.
- Variável secreta sintética do pai não entra no ambiente do filho.
- Chave privada de registro de teste é inacessível por HKCU e HKEY_USERS/SID.
- Sockets locais e externos recebem WSAEACCES; o listener local tem controle positivo.
- OpenProcess contra o pai, com direitos amplos, é recusado.
- Timeout e cancelamento encerram o processo próprio.
- Limites de saída e memória são efetivamente atingidos.
- Um descendente não continua executando quando o chamador retorna.
- Um hardlink externo dentro do staging impede a aplicação das ACLs.

### Recuperação após queda do supervisor

`SandboxJournal` grava uma reserva SQLite síncrona antes de chamar a API de
criação de perfil. O inventário fica em diretório acessível apenas ao usuário
e SYSTEM, fora dos diretórios concedidos ao candidato. Uma trava de arquivo
mantida pelo supervisor impede que outro processo limpe perfis ainda ativos.
O registro contém somente nomes do namespace `Nyx.Sandbox.<uuid>` e a localização
de armazenamento obtida do Windows. Não interpreta comandos de saída do sandbox.

Ao reabrir, valida o inventário inteiro antes de qualquer limpeza. Usa a API do
Windows somente para os perfis reservados, confere o diretório conhecido e só
remove o registro após sucesso e ausência do armazenamento anterior. Falhas
preservam a reserva para nova tentativa. A rotina não remove workspaces ou outros
diretórios recursivamente. O estado padrão fica em `data/sandbox/profiles`, ignorado
pelo Git; testes usam diários próprios temporários.

Quatro ensaios reais adicionais passaram: queda imediatamente após CreateProcess
antes da primeira instrução; queda durante execução com descendente; tentativa
do candidato de ler/corromper o diário; limpeza de perfil contendo junction para
um diretório externo de teste, cujo conteúdo foi preservado. Quatro testes do
diário cobrem exclusividade, falha/retry, inventário adulterado e caminhos indevidos.
Total focado: **18 passaram**; `build/sandbox-probes/recovery.xml`.
Regressão posterior com navegador/Windows/LPAC reais: **576 passaram, 1 pulado
em 45,64 s**; Ruff aprovado; `build/sandbox-probes/recovery-regression.xml`.

Execute no Windows, pelo ambiente do projeto:

```powershell
$env:NYX_TEST_SANDBOX='1'
.\.venv\Scripts\python.exe -m pytest tests/test_windows_sandbox_live.py
.\.venv\Scripts\python.exe tools/probe_windows_sandbox.py --registry-read
```

Relatórios locais ignorados pelo Git: `build/sandbox-probes/acceptance.xml`,
`smoke-result.json` e `loader-trace.txt`. O modo `--trace-loader` usa depuração
somente do filho criado pelo ensaio, sem alterar registro ou flags globais.
Regressão conjunta com navegador, Windows e LPAC habilitados: 568 passaram,
1 pulado em 48,42 s; `build/sandbox-probes/regression.xml`. Ruff aprovado.

## Falha de inicialização diagnosticada

Sem capabilities, o Python termina com `0xC0000022` antes do script. O rastreamento
do loader mostrou `BasepSxsCreateStreams` e consulta do contexto de ativação
recusados durante o carregamento de `python311.dll`. As ACLs de leitura/execução
dos arquivos envolvidos foram consultadas e estavam permitidas ao token.

A capability nomeada `registryRead`, documentada pela Microsoft para LPAC,
permitiu inicializar o Python. Está disponível somente por parâmetro explícito
de diagnóstico neste protótipo; não há concessão automática em uma ferramenta.
Não foram concedidas capabilities de rede ou COM. As chaves privadas de teste
continuaram inacessíveis, inclusive pelo caminho HKEY_USERS do usuário original.
Isso prova os casos ensaiados, não a inacessibilidade de todo objeto do sistema.

## Trabalho obrigatório antes da integração

- Quota/limite de escrita em disco, incluindo a área privada do AppContainer.
- Recuperação de staging/exportação após queda. Perfis LPAC já têm diário e
  recuperação real validada; pastas de projetos ainda não são geridas por ele.
- Integrar a cópia/exportação limitada de `ProjectSnapshot` ao gerenciador de
  projetos. Proteção de reparses e ensaio multifile já foram validados;
  detalhes em `PROJECT_SNAPSHOTS.md`. Recuperação das pastas ainda falta.
- Validação de processos concorrentes, escape de Job, limites de CPU/processos,
  handles, IPC, Win32k em execução e ataques a caminhos/reparse points.
- Política final de capabilities e comparação contra a fronteira de confiança
  exigida para cada tipo de plugin ou tarefa.
- Compatibilidade de extensões: `_ctypes` falhou ao importar nesta configuração;
  código Python padrão funcionou. Não liberar COM/GUI para contornar a falha.
- Empacotamento, diferenças entre versões Windows/Python e operação sem elevação.
- Integração com permissões, auditoria, ResourceGovernor e o fluxo completo de
  criação/teste/correção. Nenhuma dependência de projeto é baixada automaticamente.

LPAC compartilha o kernel do Windows; não é uma máquina virtual. Arquivos do
sistema explicitamente acessíveis a LPAC podem continuar legíveis. Os testes não
demonstram uma política de negar todo acesso fora do workspace sem exceções.

## Fontes primárias consultadas

- [AppContainer e LPAC](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
- [Launcher de referência da Microsoft](https://github.com/microsoft/SandboxSecurityTools/tree/main/LaunchAppContainer)
- [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [TerminateProcess é assíncrono](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess)

Foram consultadas também as APIs experimentais CreateProcessInSandbox. Não foram
adotadas nem usadas para alegar uma fronteira adicional neste protótipo.
