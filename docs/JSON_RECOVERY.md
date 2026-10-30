# Respostas incompletas do modelo — 28/10/2026

Atualização de 30/10: o contexto efetivo também limita a resposta. A montagem
agora reserva espaço, compacta entradas e distingue contexto cheio de teto de
saída. Recuperação por contexto cheio mantém o teto e evita acrescentar texto.
Ver [diagnóstico e evidência](RELIABILITY_2026-10-30.md).

O erro informado pelo usuário foi localizado no log de desenvolvimento às
10:48:42 (São Paulo): o JSON terminou com 453 caracteres dentro da ação
`browser/media_status`. O parser acusou vírgula ausente exatamente no fim da
saída. Outras respostas do mesmo período terminaram no meio de strings.
O log antigo não guardava `done_reason`/contagem de tokens; portanto ele comprova
a saída incompleta, mas não permite afirmar retrospectivamente seu motivo de término.

O cliente tinha teto de 512 tokens e descartava os metadados de conclusão.
Agora mantém esse teto inicial e pede conteúdo conciso. Se a saída não for JSON
válido, vier com `done=false` ou `done_reason=length`, descarta a proposta e faz
uma única nova geração, do pedido original, a temperatura zero e até 1024 tokens.
Um orçamento explícito do chamador não é aumentado. O esquema, ferramentas,
modelo e contexto permanecem os mesmos. O fragmento inválido não é reinjetado
como instrução e não recebe fechamento automático de chaves/aspas.

A regeneração compartilha o prazo original do cliente. Cada envio passa de novo
pela fila e pela admissão de memória. No TaskRunner, cancelamento, emergência e
prazo da tarefa impedem nova admissão. A fila e a admissão descontam seu tempo do
timeout HTTP. Uma requisição HTTP já enviada continua limitada por timeout;
isso não implementa cancelamento imediato do processamento no servidor Ollama.

Falha de rede não é repetida automaticamente. JSON inválido não transforma o
modelo em indisponível, nem causa troca de modelo. Após a segunda resposta
inválida, nenhuma ação dessa etapa é executada; etapas anteriores ficam no
histórico. Ações regeneradas passam pela política normal de confirmação.
JSON com chaves duplicadas, números não finitos e aliases conflitantes é recusado.
Parâmetros com tipo incorreto não são mais convertidos silenciosamente em `{}`.

A interface mostra que está gerando novamente a resposta e atualiza o resumo
de tarefas quando o pedido encerra. A auditoria `model_generation` registra
tentativa, razão de término, limite/contagem de tokens e tamanho da saída, sem
copiar respostas para esse novo evento. Não é uma avaliação da verdade semântica:
JSON bem formado ainda exige validação, políticas e verificação do resultado.

## Evidências

- `tests/test_generation_recovery.py`: corte no meio de ação, limite de duas
  gerações, confirmação de gravação, ausência de reexecução de etapas, cancelamento,
  prazo, orçamento explícito, falha de rede e rejeição de dados ambíguos.
- `tools/probe_json_recovery.py`: três cenários no Qwen3.5:4b real, sem executar
  ferramentas propostas: cumprimento, planejamento de `media_status` e corte
  injetado na primeira resposta seguido de regeneração válida. 1,83 s / 1,66 s /
  2,91 s na execução final com modelo aquecido. A operação proposta foi conferida
  como `media_status`, além do tipo `browser`. Não é teste de
  login nem de reprodução real do Spotify.
- `build/sandbox-probes/json-recovery-live.json` e `.log`: metadados do ensaio.

Referências do protocolo consultadas:
[Structured outputs](https://docs.ollama.com/capabilities/structured-outputs) e
[Chat API](https://docs.ollama.com/api/chat). O schema limita estrutura;
`done_reason` e a validação posterior continuam necessários.
