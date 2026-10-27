# Aprovação vinculada ao conteúdo de um servidor MCP

O protótipo `MCPLaunchPlan` captura arquivos imutáveis de uma pasta escolhida e
produz uma revisão com SHA-256. A revisão inclui inventário de arquivos, hashes,
entradas excluídas, origem declarada, entrada Python, argumentos, níveis por
ferramenta e limites de CPU/memória/processos/tempo/saída. Também informa que o
LPAC usa registryRead, não recebe rede/credenciais e depende de Python confiável
fornecido pelo supervisor. Hash verifica identidade dos bytes, não autoria.

Captura limitada a 64 arquivos, 4 MiB totais, 256 KiB por arquivo e profundidade
oito. Dependências realocadas para `.local-deps` são excluídas dos snapshots,
assim como ambientes e nomes sensíveis já conhecidos. Exclusões aparecem na
revisão; isso não é um detector universal de segredos.

`MCPApprovalGate.approve(plan, reviewed_digest)` é uma API do host destinada ao
fluxo de confirmação da interface, não uma ferramenta do modelo. Só aceita o
digest da revisão exata. Emite autorização de uso único por 60 segundos, ajustável
de 1 a 300, com no máximo 32 pendentes. Expira ao reiniciar o processo. Revogação,
validade e consumo são protegidos por lock; somente um consumidor vence.
Tentativa com plano divergente invalida o token. Aprovar o lançamento não aprova
chamadas de ferramentas, que continuam sujeitas à confirmação normal.

`run_approved_mcp` consome a autorização antes de criar pastas, conceder ACLs ou
executar. Materializa os bytes aprovados em nova pasta, sem reler a origem.
O código recebe leitura/execução no LPAC; uma pasta de trabalho separada recebe
escrita. Bootstrap fixo executa a entrada Python e permite importar módulos do
pacote aprovado. Não há shell nem argumentos arbitrários ao interpretador.
`plan.client_config()` deriva a política do cliente desse mesmo plano.

## Evidência

Testes unitários cobrem divergências em arquivos, origem, identificador,
argumentos, ferramentas e limites; expiração, revogação, uso único e concorrência.
Ausência de autorização impede até a criação da pasta temporária.

Ensaio real no LPAC: captura e aprovação de servidor com dois arquivos; alteração
posterior da origem; execução e chamada MCP usando somente os bytes revisados;
recusa de escrita no código aprovado; escrita de prova na pasta própria; recusa
de reutilização da autorização. O servidor de ensaio é próprio e não foi
executado diretamente no host.

Regressão: **759 aprovados, 1 pulado em 57,81 s, saída 0; Ruff aprovado**.
Relatórios: `build/sandbox-probes/mcp-approval-regression.xml` e `.log`.

## Limites desta etapa

A UI ainda não exibe essa revisão nem emite esses tokens. O ensaio fornece
aprovação somente para seu próprio candidato. A API não deve ser anunciada como
gerência de servidores pronta para o usuário.

O supervisor ainda fornece runtime Python confiável, perfil e pasta de staging.
A identidade/hash do runtime não está vinculada ao token; sua preparação e
verificação precisam ser integradas antes de expor o lançamento ao usuário.
Tokens não protegem contra código malicioso já executando no host. Cadastro
persistente, auditoria durável da aprovação, recuperação/limpeza de staging,
quota de disco e integração ao ResourceGovernor continuam pendentes. Nenhum
staging é apagado automaticamente após falha: a árvore nova fica para inspeção.
