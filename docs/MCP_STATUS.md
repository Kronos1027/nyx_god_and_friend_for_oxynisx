# MCP: política corrigida, transporte isolado pendente

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
