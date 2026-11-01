# Referências externas (aprender com elas; verifique licença antes de copiar qualquer código)

Use para **arquitetura e ideias**. Código só pode ser reaproveitado se a licença permitir, com atribuição registrada em `docs/DECISOES.md`. Confirme versão/estado atual de cada projeto antes de depender dele.

## Repositórios
| Projeto | O que aprender | Onde usar |
|---|---|---|
| **CursorTouch/Windows-MCP** (MIT, uso amplo em clientes MCP) | Ferramenta de estado que junta janelas ativas + árvore de elementos interativos + screenshot; modo DOM para conteúdo de página; **watchdog** de foco via eventos UIA; gerência de desktops virtuais; ~15 ferramentas enxutas | M1/M4: contrato compacto de desktop, UIA em processo separado, eventos de foco para Presença |
| **Open-LLM-VTuber** (companheira de voz local; cliente desktop com modo pet; v2 em reescrita) | Voz sem fone (**interrupção sem ouvir a própria voz**), pipeline VAD→STT→LLM→TTS com streaming, percepção de tela/câmera, memória de longo prazo (via Letta), modo pet transparente/click-through | M6: voz, barge-in/AEC, estrutura de companheira. Atenção: licenças de assets de terceiros |
| **microsoft/playwright-mcp** e **browser-use** | Observação do navegador por **snapshot de acessibilidade com refs**, ações por ref, espera automática | M3: formato da observação e ações por ref |
| **OmniParser** / **UI-TARS (desktop)** | Parsing de GUI por visão e grounding de cliques por coordenada | M4: apenas como último recurso de percepção |
| **openWakeWord**, **Silero VAD** | Wake word e VAD leves, locais | M6 |
| **sqlite-vec** (ou índice vetorial em arquivo), **mem0/Letta** (como referência de modelo de memória) | Memória híbrida e consolidação | M6 |
| **trafilatura / readability**, **RapidOCR**, **winsdk** (SMTC, OCR do Windows) | Extração limpa de páginas, OCR leve, mídia tocando | M3/M6 |
| **Lucide** (ISC), **Inter** e **JetBrains Mono** (OFL) | Ícones e fontes da interface | M7 |

## Modelos locais para a RTX 3060 12 GiB (confirmar disponibilidade e **medir** na bateria; fontes são blogs/comparativos, não verdade final)
- `qwen3.5:9b` — ~6,6 GiB em Q4; tool calling nativo em campo separado (`tool_calls`), ~100 tok/s em GPU de classe superior; candidato principal.
- `gemma4:12b` — multimodal (texto, imagem, áudio, vídeo), contexto longo; um comparativo cita ~6,6 GiB em Q4 e prefill rápido, outro sugere folga maior com 16 GiB. Medir.
- `qwen3-vl:8b` — visão para screenshots/UI sob demanda (carregar, usar, descarregar).
- `Ministral 3 14B` — focado em agentes/ferramentas; apertado em 12 GiB com contexto grande.
- `qwen3.5:4b` — rápido para o perfil Jogo/Live.
Critério de escolha: taxa de sucesso na bateria real, tokens/s, VRAM/KV em 8K–16K, obediência ao formato de tool call.

## Sobre o Codex (como esta configuração foi desenhada)
`AGENTS.md` (< 32 KiB) guarda regras duráveis; skills em `.agents/skills/<nome>/SKILL.md` guardam procedimentos repetíveis com descrição focada e arquivos de apoio carregados sob demanda; o prompt da tarefa descreve o resultado, as entradas, as verificações e o ponto de parada. Boas práticas oficiais: planejar primeiro em tarefas difíceis, nível de raciocínio alto para trabalho longo/agêntico, regras de aprovação ligadas a ações específicas e **critério explícito de conclusão**.
