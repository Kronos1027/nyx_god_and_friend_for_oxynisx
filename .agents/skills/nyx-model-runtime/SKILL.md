---
name: nyx-model-runtime
description: Escolher e orçar o modelo local da Nyx (Ollama), contexto, KV cache, perfis Normal/Jogo/Foco, roteador conversa×agente e tool calling nativo na RTX 3060 12 GiB.
---

# Modelo, contexto e recursos

Arquivos: `src/core/runtime_budget.py`, `src/core/llm_client.py`, `src/core/personality.py`, `src/core/task_runner.py`.

Problemas conhecidos a corrigir: orçamento = VRAM livre − 4 GiB e barrado por RAM livre; contexto ≤ 4096; saída ≤ 512; JSON de 7 chaves em todo turno; catálogo inteiro de ferramentas a cada passo.

- Orçamento **por VRAM**: `VRAM_total − reserva_do_perfil − KV(ctx)`. RAM livre só como piso duro baixo; ao recusar, listar quem consome RAM e oferecer descarregar o que é da Nyx (Whisper/Kokoro/modelos).
- Contexto padrão 8192, estendido 16384 no perfil que permite; `OLLAMA_KV_CACHE_TYPE=q8_0`; flash attention só se passar num smoke test (já houve crash; ver `HANDOFF_DSH.md`); `think` controlado por tipo de tarefa; saída por orçamento (conversa 512, plano 1024, código/resumo 2048+).
- **Roteador conversa × agente**: conversa em texto livre com streaming (sem schema); agente com **tool calling nativo** (`/api/chat` `tools`) e schema mínimo de fallback; `emotion` e confirmações calculados pelo código. Poda de ferramentas por intenção (3–6), prefixo de prompt estável, resumo rolante do histórico.
- **Perfis**: Normal (modelo principal residente, ctx 8–16K), Jogo/Live (modelo ≤ ~4 GiB ou CPU, ctx 4K, sem fundo), Foco. Detecção automática (Steam/fullscreen/OBS) + override.
- **Escolha de modelo por evidência**: benchmarkar candidatos que caibam (ver `docs/REFERENCIAS.md`: p. ex. `qwen3.5:9b`, `gemma4:12b`, `qwen3-vl:8b` para visão; confirmar disponibilidade no momento) na bateria real e gravar `docs/evidence/model_bench_*.json`. Fallback é sempre **explícito** na UI.
- Fila de inferência com prioridades (voz/conversa > tarefa em foco > fundo) e posição da fila visível.
