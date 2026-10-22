# Programação local — 22/10/2026

Modelo instalado: `nyx-coder:9b`, baseado em Qwen3.5 9B quantizado,
Ollama 0.40.6, contexto 65536. Observação na RTX 3060 12 GB:
aproximadamente 6,9 GB de VRAM alocados, totalmente na GPU.
Nyx continua usando seu modelo preferido configurado, Qwen3.5 4B.

## Abrir

- DeepSeek Harness: execute `E:\projeto\local-coding\Start-DeepSeekLocal.ps1`.
  Abra uma conversa nova com `ollama-local / nyx-coder:9b`.
- Codex: `E:\projeto\local-coding\Start-CodexLocal.ps1`.
  A integração do aplicativo também foi configurada via `ollama launch chatgpt`.
  O teste de execução de ferramentas no Codex **ainda não passou**.
  As alegações do modelo sobre bloqueio de política não demonstram, por si,
  a causa. Não considerar o fluxo de programação Codex validado.

O Harness local leu dois arquivos, corrigiu uma divisão inteira e executou
dois testes Python com sucesso no diretório de teste em C:. O teste no E:
encontrou erro Windows `SetNamedSecurityInfoW`, Win32 5, na concessão de
escrita do sandbox. Não desativar a proteção para contornar esse erro.
Isso ainda limita o uso do Harness diretamente no projeto em E:.

Somente pedidos enviados ao provedor Ollama são locais. A escolha de outro
provedor pode consumir sua franquia. O modelo local não equivale ao Astra.
As ferramentas e a qualidade do código exigem revisão e testes.

Os scripts de inicialização desta máquina estão copiados em
`tools/local_coding/`. Não incluem credenciais, conversas ou bancos do Codex.
São cópias de recuperação, com caminhos desta máquina; não constituem um
instalador portátil. O catálogo e os perfis instalados permanecem locais.

Referências oficiais:
- https://docs.ollama.com/integrations/chatgpt
- https://docs.ollama.com/integrations/codex
- https://docs.ollama.com/integrations/deepseek-harness

## Voz e iniciativa

Kokoro ONNX usa Dora (`pf_dora`, pt-BR) em CPU com dois threads e espera
sem spinning. Amostra real gerada em 5,09 segundos incluindo inicialização:
2,86 segundos de áudio a 24 kHz. Não há garantia de timbre de anime.
Implementação da sessão: https://github.com/thewh1teagle/kokoro-onnx/blob/main/examples/with_session.py

A configuração “Nyx pode iniciar uma conversa nos intervalos” permite um
convite após cinco minutos sem pedidos. Há intervalo mínimo de 30 minutos,
até três convites por sessão/dia, das 9h às 21h. Sem nova interação, não
repete o convite. Modo foco, composição de mensagem, tarefa e escuta adiam
os convites. São convites predefinidos; não são observação contínua nem
conversação generativa autônoma.

O agente recebe os parâmetros reais dos templates de shell e omite ferramentas
bloqueadas pelo circuito de falhas. Recupera até duas notas relacionadas ao
pedido, com fontes e indicação de não verificadas. Isso é consulta à memória,
não treinamento dos pesos nem reprogramação automática do aplicativo.
