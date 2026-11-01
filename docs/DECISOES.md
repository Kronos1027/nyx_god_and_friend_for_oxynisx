# DECISOES — registro de decisões reversíveis (uma entrada por decisão)

## D-006 · Scanner offline isolado e serial · 01/11/2026

Contexto: CI não colecionava sem Qt e não havia barreira de segredos no commit.
Escolha: requisitos CPU/testes GUI opcionais e detect-secrets/pre-commit isolados
no volume do projeto; todos os plugins, baseline auditado por candidato,
verificação de credenciais na rede desativada. Scan serial limita concorrência
de memória. Medição de startup até0,779s/~55MiB RSS por CLI. Reversão: reverter
arquivos/configuração e retirar somente o hook local instalado nesta sessão;
não remover dados do usuário nem alterar backups/credenciais.

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

## D-003 · Suspender envios públicos após aprovação · 01/11/2026

Contexto: GitHub confirmou público e branch de backup existente. Proposta em
PROPOSTA_BACKUPS.md aprovada explicitamente pelo usuário. Escolha: suspender
uploads no código e desativar a preferência nos INIs de fonte/instalação;
preservar timer local, backups, chave e branch remota. Motivo: autorização cobre
suspensão de novos envios, sem migração/remoção. Reversão: requer decisão futura
e destino privado verificado; nenhuma opção de UI contorna a suspensão atual.
Instâncias antigas já abertas não foram reiniciadas ou atualizadas à força.

## D-004 · Aprovação de ensaio só no diálogo de produção · 01/11/2026

Contexto: adapters isolados não exercitam a experiência completa. Escolha:
DesktopWindow/OverlayWindow temporários, modelo real, QTest clicando o botão
do PermissionDialog real e observação Win32 em módulo independente. Motivo:
9/9aberturas de três apps observadas, com uma confirmação cada. Guardas negam
outras ações; não se liga Autônoma nem se opera a Nyx pessoal. Reversão: remover
o harness/rota de bench, sem modificar comportamento ou dados do produto.

## D-005 · Não fechar apps pessoais para melhorar o gate · 01/11/2026

Contexto: repetições observaram apps já abertos; fechamento poderia afetar o
uso do PC. Escolha: preservar os apps e marcar gate_eligible=false, mostrando
already_visible_before e cobertura faltante. Motivo: nove passes parciais não
são o gate de15apps com reset. Reversão: acrescentar depois cleanup de fixtures
cuja propriedade e segurança possam ser comprovadas, mantendo confirmações R3.
