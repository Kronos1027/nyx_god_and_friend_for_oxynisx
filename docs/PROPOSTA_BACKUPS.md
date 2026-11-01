# Proposta para os backups — decisão pendente

01/11/2026. Consulta de metadados GitHub confirmou repositório público e a
existência da branch `nyx-backups`. Essa branch é usada pelo mecanismo existente
de cópia criptografada; não foram lidos/descriptografados os backups nem auditado
todo seu histórico. Não alteradas configurações, chaves, arquivos ou refs remotas.

## Ação recomendada para aprovação

**Suspender novos envios automáticos ao repositório público**, preservando os
backups locais criptografados, a chave e a branch remota existente. É reversível
pela preferência de backup em nuvem; não libera nem apaga dados. Depois preparar
um destino privado e uma migração separada, sem remover a origem até verificar
o novo destino e obter aprovação específica.

Essa suspensão impede novas cópias nesse destino; não retira os arquivos que já
estão no histórico público. Apagar refs ou reescrever histórico não faz parte
desta proposta. Nenhuma chave será enviada pelo chat ou versionada.

Alternativa: manter o comportamento existente enquanto se define um destino
privado. Nesse caso os envios que já estiverem habilitados continuam possíveis.

Dependência: aprovação do usuário em AGENTS.md§10, item5, antes de mudar qualquer
comportamento/configuração de backup. Toda implementação independente continua.
