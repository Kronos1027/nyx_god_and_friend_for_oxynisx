# DECISOES — registro de decisões reversíveis (uma entrada por decisão)

Formato: `## D-NNN · título · data` → Contexto · Opções · Escolha · Motivo (com dado medido) · Como reverter.

## D-001 · Adotar o pacote sem reiniciar o trabalho · 01/11/2026

Contexto: pacote novo descreve M0–M8; já existem correções/evidências em commits.
Opções: substituir o projeto, reiniciar de main ou criar branch a partir do estado
atual. Escolha: `nyx-2` derivada de `5fc8ee5`, arquivos do ZIP somente onde não
existiam. Motivo: preservar 913 passes e os resultados/falhas reais, sem presumir
que isso conclui os novos gates. Reversão: branch anterior continua disponível;
novos documentos podem ser revertidos por commit, sem apagar dados locais.

## D-002 · Mínimos da bateria e evidência herdada · 01/11/2026

Contexto: cabeçalho pede40 tarefas; categorias enumeram50. Escolha: manifesto50,
três execuções e verificadores independentes. Testes antigos e adapters diretos
continuam evidência diagnóstica, sem promovê-los a aceite completo do planejador.
Motivo: não reduzir cobertura/afrouxar gate. Reversão: alteração explícita da
especificação pelo usuário; métricas antigas permanecem identificadas.

## D-003 · Backups aguardam decisão, demais frentes continuam · 01/11/2026

Contexto: GitHub confirmou público e branch de backup existente. Escolha: proposta
revisável em PROPOSTA_BACKUPS.md e nenhuma alteração em backup/credenciais enquanto
aguarda resposta, conforme AGENTS§10. Motivo: não há autorização nova para migrar,
suspender ou apagar o backup. Reversão: executar somente a opção que for aprovada.
