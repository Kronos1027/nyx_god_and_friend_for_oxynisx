# Tarefas com vários passos

A interface Windows usa TaskRunner para decidir, executar, observar e decidir novamente. Cada decisão continua passando por AgentLoop, ToolRegistry, política de confirmação, circuit breaker, verificador e auditoria existentes. A CLI mantém o ciclo anterior de uma ação.

## Limites e resultados

- Até seis ações e 180 segundos por pedido, incluindo espera por confirmação. O prazo é cooperativo: não encerra à força uma operação ou geração já iniciada. Antes de cada nova ação, o prazo e o cancelamento são verificados.
- Uma ação idêntica consecutiva é bloqueada antes da execução; uma mesma chamada pode ocorrer novamente após outra ação, permitindo ler, alterar e reler. Uma terceira ocorrência é bloqueada. Esses limites ainda podem interromper tarefas legítimas longas e precisam de avaliação por tipo de tarefa.
- Observações são dados externos limitados em tamanho; histórico de planejamento é limitado. Não concedem autoridade para mudar o pedido ou as políticas. Proteção por instruções não prova resistência completa a prompt injection.
- Cada ação sensível/destrutiva segue a política atual. A confirmação fica vinculada à tarefa e aos parâmetros exatos. Confirmar uma etapa não aprova a próxima; alterar ou reutilizar a confirmação é recusado.
- A interface mostra etapa, ferramenta, resultado da verificação e prévia limitada. O botão Interromper solicita cancelamento; Ctrl+Alt+K também bloqueia controle de tela e solicita cancelamento. Ações já executadas não são desfeitas automaticamente.
- Encerramento do planejamento pelo modelo não prova sucesso do objetivo. Falhas e resultados não verificados recebem aviso na resposta. Se o verificador falhar depois que a operação começou, o resultado permanece explicitamente desconhecido.
- O histórico de conversa registra o pedido original e a resposta final; passos intermediários ficam na auditoria. Não há retomada automática de efeitos após reiniciar o aplicativo. Persistência de tarefas e reconciliação de ações incompletas continuam pendentes.

## Evidência

Testes executam operações reais em arquivos temporários e planejamento roteirizado, incluindo dois arquivos, leitura/alteração/releitura, confirmações sucessivas, recusa, confirmação adulterada, repetição, orçamento, prazo, cancelamento na UI e falha do verificador. Isso valida execução e controle; não comprova qualidade do planejamento do modelo local.

`tools/verify_task_runner.py` testa o modelo local real com dois arquivos temporários de conteúdo conhecido. As tentativas desta revisão foram adiadas porque o orçamento conservador de memória não admitiu nenhum modelo: aproximadamente 0,7–1,9 GiB de RAM livre, com os modelos Ollama descarregados. O teste deve ser repetido quando houver recursos; não foram reduzidas as reservas nem encerrados aplicativos do usuário para forçar aprovação. O relatório registra explicitamente `real_model_validated=false`.

## Escrita, releitura e recuperação — 2026-10-21

A verificação de write_file agora exige igualdade exata dos bytes UTF-8 solicitados. Existência de arquivo, conteúdo antigo de mesmo tamanho e diretórios não bastam. Caminhos relativos são verificados no caminho absoluto resolvido pela ferramenta sandbox, não no diretório de trabalho do processo. Arquivos vazios válidos são aceitos. A leitura de verificação é limitada ao tamanho esperado mais um byte, respeitando MAX_WRITE_BYTES.

TaskRunner detecta propostas repetidas antes de exibir nova confirmação. São permitidas até duas tentativas adicionais de planejamento por tarefa, sujeitas ao prazo original; nenhuma delas executa a ação rejeitada. A proteção imediatamente anterior à execução continua ativa. Confirmações e políticas não são removidas.

O diagnóstico tools/verify_file_workflow.py usa FileTool de produção em pasta temporária, conteúdo aleatório e uma aprovação roteirizada restrita ao arquivo/conteúdo exatos do teste. Não é aprovação geral nem teste de clique humano no diálogo. Exige arquivo exato, escrita e leitura verificadas nessa ordem, uma confirmação e entrega do código na resposta final.

Resultados observados:
- Antes da recuperação: Qwen3.5 4B repetiu a escrita; execução repetida foi bloqueada. Falha em 9,53 s.
- Com recuperação: arquivo gravado e relido, mas código omitido na resposta. Falha em 16,11 s.
- Com orientação de entrega final: Qwen3.5 4B concluiu os cinco critérios em 19,56 s, com duas tentativas de replanejamento. Código observado: 35a5399ddf.
- Nova execução selecionou Qwen2.5 3B e propôs uma escrita fora dos parâmetros exatos do ensaio; a aprovação roteirizada recusou, sem ação executada. Falha em 12,19 s. A seleção de modelo por orçamento ainda não considera competência por tipo de tarefa.

Os últimos ensaios são preservados individualmente em build/previews/file-attempts. O arquivo file-workflow.json mostra a tentativa mais recente, inclusive quando falha. Sucesso isolado não demonstra confiabilidade geral. Próxima lacuna: evitar troca silenciosa para um modelo que não foi aprovado para a capacidade necessária e avaliar a contabilização de modelos já residentes no orçamento.
