# Voz local: recursos e validação

## Mudanças

- Reconhecimento com faster-whisper usa a mesma fila FIFO da conversa: uma inferência ativa, até duas esperando e espera máxima de 45 segundos. O slot permanece ocupado durante a iteração dos segmentos, pois o decodificador trabalha de forma lazy.
- `auto` usa CPU int8, com um worker e no máximo quatro threads. CPU explícita também usa int8. A detecção não importa mais PyTorch. CUDA explícita continua disponível, com reserva própria; fallback CPU exige nova checagem de RAM. Erros da CPU não provocam uma segunda tentativa idêntica.
- Antes de carregar, reserva 2 GiB livres para o sistema mais um envelope conservador: tiny/base 1 GiB, small 2 GiB, medium 5 GiB, demais 8 GiB. São limites de admissão, não picos medidos. Reuso exige pelo menos 2 GiB livres. CUDA também reserva 4 GiB de VRAM mais o envelope de carga. Telemetria ausente não autoriza carregar voz.
- Captura limitada a 30 segundos em 16 kHz. Transcrição aceita somente vetor mono float, finito e com até 480 mil amostras. O fluxo gráfico atual grava 3,5 segundos por acionamento.
- A interface informa falta de memória ou fila ocupada, em vez de atribuir todo erro ao microfone.

Referência do backend e precisão CPU: https://github.com/SYSTRAN/faster-whisper . As opções foram também conferidas na versão instalada, 1.2.1.

## Evidência local, 2026-10-21

Fixture sintetizada localmente com Windows SAPI Maria, sem microfone e sem envio de áudio: “Olá, minha amiga. Quanto é vinte mais trinta?”. Modelo small já presente no cache; execução com HF_HUB_OFFLINE=1.

- Áudio de 5,648625 s, transcrito em 5,45 s incluindo carga inicial, CPU.
- Resultado: “Olá, minha amiga. Quanto é 20 mais 30?”
- RAM livre antes/depois: 4.544.462.848 / 4.282.028.032 bytes. Amostras pontuais, não pico.
- Primeiro avaliador exigia números por extenso e marcou falha. Resultado original preservado em build/previews/voice-live-smoke.json. O avaliador corrigido aceita palavras ou números inteiros completos; o texto original passa nessa checagem.
- Segunda tentativa com o diagnóstico reproduzível tools/verify_voice.py: recusada antes da carga por RAM livre de 4.184.223.744 bytes, abaixo do limiar de 4 GiB. Relatório preservado em build/previews/voice-attempts/ef5bfe5c8d3745ea98c605df60378906.json.

Os testes simulados cobrem carregamento único, CPU int8, cache, VRAM/RAM insuficiente, fallback, exclusão com a conversa, erro do iterador liberando a fila e entradas inválidas. O diagnóstico aceita a fixture em --audio e grava cada tentativa separadamente; não é avaliação geral de qualidade linguística.

## Ainda pendente

Microfone real, sotaques/ruído, fala longa, conversa por voz de ponta a ponta, qualidade da voz sintetizada e latência sustentada. A fila coordena STT e chamadas Ollama desta aplicação; TTS, llama.cpp e processos externos ainda não têm a mesma coordenação. O modelo STT permanece em cache; não há descarregamento por inatividade. Limites não interrompem instantaneamente uma chamada nativa travada.

## Interrupção da fala e uso do microfone

A fila de TTS agora usa gerações e eventos por fala. Parar em repouso não descarta a próxima resposta; parar invalida itens antigos, inclusive os já retirados da fila pelo worker. Não há mais uma thread observadora por frase. O worker sobrevive a erros, shutdown é idempotente e novas falas após encerramento são ignoradas. Texto para síntese fica limitado a 3 mil caracteres e oito itens pendentes.

O fluxo gráfico abre uma sessão de microfone que cancela a fala atual, suprime novas falas e aguarda até três segundos pelo worker ficar ocioso. Se não terminar, a captura não começa e a interface informa a causa. A suspensão dura até terminar a transcrição. Isso é coordenação de turnos, não cancelamento acústico de eco; áudio de outros aplicativos continua possível.

SAPI usa Speak assíncrono com texto simples, consulta WaitUntilDone a cada 50 ms e solicita purge ao cancelar. Referências oficiais: https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee125223(v=vs.85) e https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee125654(v=vs.85) . Kokoro ainda não interrompe a chamada nativa create no meio; uma síntese demorada pode impedir temporariamente a captura, mas o resultado cancelado não inicia reprodução.

Validação: 345 testes aprovados, um ignorado, aviso conhecido COM; Ruff aprovado. Casos cobrem parada ociosa, cancelamento, fila, pausa aninhada, timeout antes da captura, erros e encerramento. Teste com SAPI real redirecionado para WAV: fala de 23 mil caracteres cancelada por timer de 150 ms, chamada async seguida de purge, duração total 0,234 s. Esse ensaio do backend excedeu deliberadamente o limite público de 3 mil caracteres para manter fala pendente. A primeira tentativa falhou por assinatura incorreta do wrapper de teste; corrigida na segunda tentativa. Relatórios preservados em build/previews/sapi-cancel.json e sapi-cancel-corrected.json. Nenhum som foi reproduzido nem microfone capturado nesse teste.
