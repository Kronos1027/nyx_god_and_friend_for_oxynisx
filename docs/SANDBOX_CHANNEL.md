# Canal interativo do protótipo LPAC

`run_lpac(..., channel=SandboxChannel())` aceita entrada incremental e publica
chunks de stdout enquanto o processo isolado está ativo. Um consumidor pode
executar o supervisor em uma thread, aguardar uma resposta e enviar a próxima
mensagem. Sem canal, o comportamento anterior com stdin NUL permanece.

O canal é usado uma vez. Entrada aceita somente bytes, até 16 KiB por envio,
32 envios pendentes e 1 MiB total na sessão. Envio não espera espaço: fila cheia
gera erro para o chamador. Saída tem 32 chunks pendentes; consumidor que não a
drena provoca `channel_backpressure` e encerramento do job. Recepção tem espera
limitada a cinco segundos por chamada. O chamador deve montar suas mensagens:
chunks não correspondem necessariamente a linhas nem a mensagens JSON completas.

Com canal, stdout e stderr são separados; somente stdout entra na fila.
Ambos contam para o orçamento agregado de saída. O resultado final inclui
`output` e `stderr` limitados. Nenhuma saída do candidato é executada no host.

O supervisor cria um named pipe de nome aleatório, instância única, rejeitando
clientes remotos, com DACL do usuário/SYSTEM. Abre o lado leitor antes de lançar
o candidato e herda exclusivamente esse handle como stdin. O lado escritor fica
no host e usa I/O overlapped: um candidato que não lê não bloqueia a verificação
de prazo/cancelamento. Buffer e OVERLAPPED permanecem vivos até a conclusão;
CancelIo e descarte acontecem na mesma thread supervisora. Falha síncrona de
escrita não é confundida com operação pendente.

O lançamento continua suspenso até verificar token, LPAC, capabilities, Job e
mitigações. Limites de CPU, memória, processos, duração e saída continuam ativos.
Nenhuma capability de rede ou de GUI foi adicionada. O Python de ensaio continua
precisando da capability diagnóstica registryRead já documentada no protótipo.

Evidências reais no Windows:

- Processo Python no LPAC anuncia prontidão, recebe `ola` e `fim`, e responde
  após cada mensagem; evidências de isolamento permanecem verdadeiras.
- Processo que não lê stdin, com 512 KiB enfileirados, é cancelado e encerrado.
- stderr não aparece como stdout; excesso em stderr respeita o limite agregado.
- Saída não consumida encerra o job por backpressure.
- Cinco execuções interativas verificam liberação dos handles do supervisor.
- Pipe cujo leitor fechou rejeita escrita e encerra sem esperar uma operação
  que nunca foi iniciada.

`build/sandbox-probes/channel-live.xml` registra os 25 testes iniciais do canal
e LPAC. O caso adicional de pipe fechado está em `tests/test_sandbox_channel.py`.

Regressão final: **732 aprovados, 1 pulado em 51,96 s, saída 0**; Ruff dos
arquivos alterados aprovado. `build/sandbox-probes/channel-final.xml` e `.log`.

SandboxRPC agora fornece framing JSON-RPC, IDs, handshake, paginação/notificações
e deadlines ao cliente MCP nos ensaios isolados; ver `MCP_STATUS.md`. Isso não
completa T9: aprovação vinculada ao lançamento, gerência/UI e integração ao
runtime ainda faltam. Inicialização direta no host permanece bloqueada. Quota
de disco, recuperação de staging e qualificação ampliada também são pendentes.

Fontes: [CreateNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea)
e [I/O overlapped](https://learn.microsoft.com/en-us/windows/win32/ipc/synchronous-and-overlapped-input-and-output).
