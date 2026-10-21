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
