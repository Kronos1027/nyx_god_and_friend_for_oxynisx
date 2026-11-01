# Proposta para os backups — suspensão aprovada e aplicada

01/11/2026. Consulta de metadados GitHub confirmou repositório público e a
existência da branch `nyx-backups`. Essa branch é usada pelo mecanismo existente
de cópia criptografada; não foram lidos/descriptografados os backups nem auditado
todo seu histórico. Não alteradas configurações, chaves, arquivos ou refs remotas.

O parágrafo acima descreve a consulta inicial. Depois, o usuário aprovou
explicitamente **“Suspender novos envios públicos (recomendado)”** nesta conversa.
Aplicação e evidências abaixo; a migração privada e remoção remota continuam fora
do escopo aprovado.

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

## Aplicação em 01/11/2026

- `CloudBackup.upload` agora bloqueia antes de ler/copiar/stage/push. Checkbox de
  nuvem fica desligado e desabilitado; timer de backup local continua ativo.
- Preferência cloud_backup passou de true para false nos INIs existentes de
  desenvolvimento e instalação. Outras preferências e metadados dos backups/chave
  permaneceram iguais. Nenhum dado/branch/chave foi movido, excluído ou publicado.
- Três snapshots Fernet reais em pasta descartável tiveram envio bloqueado;
  bytes dos snapshots e chaves permaneceram iguais e nenhuma pasta cloud-backup
  foi criada. Verificação independente por arquivos; não usa mock ou Git real.
- A instância pessoal não foi reiniciada. Um executável antigo ou módulo já
  carregado antes da alteração pode manter a lógica anterior até ser reiniciado
  numa versão atualizada. Não foi instalada uma nova build nesta rodada.
- Evidências: evidence/backup_suspension_2026-11-01.json e
  evidence/backup_preferences_2026-11-01.json. Chaves e valores de outras preferências
  não aparecem nos relatórios.
- Regressão: 915 aprovados,27 pulados,zero falhas em56,581s,saída0; Ruff limpo.
  Windows/browser reais habilitados,LPAC opt-in pulado. Fonte local:
  build/diagnostic/backup-suspension-final.xml.
