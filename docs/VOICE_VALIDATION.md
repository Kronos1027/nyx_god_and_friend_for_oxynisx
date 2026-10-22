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
