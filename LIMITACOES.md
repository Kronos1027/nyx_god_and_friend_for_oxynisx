# LIMITACOES.md — limitações reais, sem contorno silencioso

> Regra do prompt mestre (seção 1): bloqueio real vai pra cá com o erro
> exato, depois de ~2 tentativas de abordagens diferentes. Nada de solução
> fake pra "seguir em frente".

## L1 — Ambiente de desenvolvimento não é o Windows alvo (estrutural)

O desenvolvimento inicial está acontecendo em um ambiente **Linux** sem GPU
NVIDIA, sem PowerShell e sem as libs exclusivas de Windows
(`pywinauto`, `PyQt6` overlay, `faster-whisper` com áudio real). Consequência
honesta:

- Tudo que é multiplataforma (allowlist, sandbox, GBNF/validação, auditoria,
  loop, macros) é **testado de verdade** — 111 testes + CI Linux.
- O que SÓ existe no Windows alvo está **pendente de validação real** e
  marcado como tal no STATUS.md:
  - comportamento do Qwen2.5-7B real com a gramática GBNF (os 20 prompts da
    Fase 1);
  - execução do dialeto powershell dos templates;
  - overlay PyQt6 renderizado (Fase 2) e sua captura de tela;
  - transcrição real do faster-whisper (Fase 3);
  - automação pywinauto (Fase 4);
  - leitura de VRAM/RAM (Fase 6).

Não é um bloqueio de código — é um limite de ambiente, tratado com
honestidade em vez de testes fingidos.

## L2 — Validação dos 20 prompts contra o modelo real: PENDENTE

A definition of done da Fase 1 pede "20 prompts variados, 0 falhas de parse"
com o modelo real. O que existe hoje:

- gramática `schema.gbnf` pronta e sanity-checkada;
- validador Python testado com 20+ payloads variados (camada 2);
- `OfflineLLM` para exercitar o ciclo SEM modelo — claramente rotulado como
  "não é o modelo real" no CLI e nos testes.

O que falta: baixar o GGUF na máquina Windows, rodar os 20 prompts com
`llama-cpp-python` + CUDA e colar o log aqui. Tentativa de contorno no
ambiente Linux (instalar llama-cpp-python CPU + modelo pequeno) foi avaliada
e descartada: validaria outro modelo, em outra máquina, com outra
quantização — prova fraca com custo alto. A prova forte é no alvo.

## L3 — pywinauto não instala em Linux (esperado)

`pip install pywinauto` falha fora do Windows (dependência de
`pywin32`/comtypes). Impacto: nenhum — `ui_tool.py` é stub da Fase 4 e o
import é lazy; o CI não toca nele.

## L4 — Confirmação por UI ainda não existe (Fase 5)

O loop devolve `needs_confirmation` + `pending_action` + o comando exato, e
o CLI faz a ponte via terminal. O `permission_dialog.py` PyQt6 (clique real
na overlay) é Fase 5 — até lá, a "UI" é o terminal. A regra de que
confirmação nunca vem de texto interpretado pelo LLM já é aplicada pelo
design do loop (`confirm_pending` é chamado pela UI, não pelo LLM).

## Itens futuros (fora do escopo inicial — não implementar sem alinhar)

- **Consciência de tela via OCR/visão** para automação de UI mais confiável
  (objetivo de médio prazo citado no prompt mestre — fica documentado aqui,
  fora do escopo inicial).
- Wake word dedicada ("Ei, Nyx") com openWakeWord/Porcupine — Fase 3 decidirá
  entre isso e trigger manual por hotkey, conforme budget de VRAM.
