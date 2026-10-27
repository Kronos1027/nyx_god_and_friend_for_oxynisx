# MCP: protocolo exercitado dentro do LPAC

Atualização: 27/10/2026. O cliente aceita SandboxRPC fornecido por um supervisor
LPAC, sem iniciar comandos no host. Sem transporte, start falha; connect_all
ainda não cria sessões isoladas. Não há conexão ao desktop/CLI.

O supervisor agora dispõe de plano de conteúdo imutável e aprovação local de
uso único, consumida antes do lançamento. O ensaio executa somente os bytes
aprovados mesmo após mudar a origem; detalhes em `MCP_APPROVAL.md`. Falta ligar
essa API à UI, além das pendências abaixo. A revisão agora inclui os bytes e
hashes do runtime Python, materializado junto do servidor; origem permanece
declarada, não autenticada.

- Protocolo suportado: **2025-11-25**. Outra revisão ou ausência de tools é
  recusada. Instruções opcionais do servidor não são promovidas ao planejador.
- JSON-RPC por linha, UTF-8 estrito, IDs correlacionados, rejeição de chaves
  duplicadas/números não finitos; limites de 64 KiB por linha e 16 KiB por envio.
- Uma requisição ativa; deadline de 0,05–30 segundos inclui inicialização.
  Progresso não estende prazo. Flood de notificações encerra a sessão.
- Ping é respondido; sampling, roots e demais capacidades são recusadas.
- Inventário limitado a oito páginas/128 nomes, sem cursor ou nomes repetidos.
- Timeout/cancelamento solicita parada do job. A notificação de cancelamento é
  enfileirada quando possível; parar o processo não depende de sua recepção.
  close solicita parada, e channel.closed confirma término pelo supervisor.
- Falha após envio recebe outcome_unknown. Campos do servidor não substituem
  metadados internos; resultados permanecem dados externos não confiáveis.

A fixture própria tools/mcp_test_server.py rodou somente dentro do LPAC:
handshake, duas páginas, echo com Unicode, allowlist, sampling negado, timeout e
cancelamento. Os três cenários terminaram o supervisor com evidências de
isolamento válidas. Nenhum servidor de terceiros foi instalado/executado.

O primeiro ensaio completo teve 745 aprovados, uma falha e um pulado: contagem
de handles no processo compartilhado com GUI/outros workers. Medição isolada,
sem aumentar tolerância, registrou **208 handles antes e após cada uma de dez
execuções** em build/sandbox-probes/handle-isolated.xml. Relatório anterior
preservado em build/sandbox-probes/mcp-isolated-regression.xml.

T9 continua parcial: faltam vínculo de aprovação com identidade/hash/lançamento,
UI, configuração persistente, credenciais, integração ao planejador/governador
e reconciliação. command/env não são executados/transmitidos pelo cliente.
Não há transporte HTTP nem exceções de rede/localhost; o ensaio usa LPAC sem
capabilities de rede. SDK Python ainda não instalado; suporte a outras revisões
e sua adoção precisam de avaliação. Não afirmar suporte universal a MCP.

Referência desta implementação: [lifecycle MCP 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

Regressão final: **747 aprovados, 1 pulado em 72,67 s, saída 0; Ruff aprovado**.
`build/sandbox-probes/mcp-isolated-final.xml` e `.log`.

## Histórico da auditoria de 25/10/2026 (antes da integração ao canal)

O módulo `src/tools/mcp_client.py` não está registrado no desktop/CLI. A auditoria
de 25/10/2026 encontrou JSON-RPC legado por stdio que iniciava qualquer comando
configurado com permissões do usuário, herdava o ambiente, esperava em readline
sem deadline e não correlacionava respostas. Allowlist vazia liberava tudo e
os níveis padrão divergiam entre chamada e registro. Os dois testes anteriores
usavam apenas sessões simuladas.

Correções implementadas:

- `start()` não inicia processos: retorna falha explícita até haver transporte
  isolado e aprovação de servidor. Não há opção para desativar esse bloqueio.
- Allowlist vazia nega tudo; ferramenta sem nível explícito é proibida.
- Configuração valida nomes, limites, tipos e níveis, copiando os campos para
  coleções imutáveis. Alterar as coleções originais não muda a política.
- Descoberta e registro conferem allowlist/nível; nomes malformados são descartados.
- Toda ferramenta registrada exige confirmação exata pelo fluxo normal da Nyx,
  inclusive no modo autônomo. Descrições do servidor não são publicadas como
  instruções no registro; o texto publicado é produzido localmente.
- Resultados são marcados como dados externos não confiáveis. Isso identifica
  proveniência, não comprova neutralização de prompt injection.

Nível 0 descreve leitura declarada; não prova comportamento nem dispensa
confirmação. Registrar comando/configuração não autoriza executá-lo.

**12 testes unitários de política** passaram. Regressão: **723 aprovados,
1 pulado em 51,31 s, saída 0**, em `build/sandbox-probes/mcp-policy-regression.xml`
e `.log`. Ruff dos arquivos alterados aprovado. Nenhum servidor externo foi
instalado/executado. Esses resultados não completam a aceitação MCP T9.

Ainda necessários: transporte interativo isolado com stdin/stdout limitados,
deadline/cancelamento, correlação de IDs, notificações e encerramento da árvore;
servidor próprio real de ensaio; inventário/aprovação na UI; restrições de rede e
localhost; credenciais seguras; integração com planejador e configuração persistente.
O protótipo LPAC ganhou entrada interativa limitada e stdout/stderr separados;
ver `SANDBOX_CHANNEL.md`. Ainda falta conectá-lo ao protocolo/cliente MCP. O
modo sem canal continua usando stdin NUL; não basta substituir Popen.

O SDK Python MCP não está instalado. Avaliar sua adoção junto do transporte:
seu subprocesso padrão não substitui sandbox. O adaptador legado permanece sem
qualificação; não reativar sua leitura bloqueante para contornar esse requisito.

Referência: [stdio na especificação MCP](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/stdio.mdx).
Mensagens JSON-RPC por linha e separação entre stdout e stderr definem o canal,
mas não fornecem isolamento do processo.
