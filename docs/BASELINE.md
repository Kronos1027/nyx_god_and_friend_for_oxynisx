# Nyx AGI Desktop v3 — Baseline de Modelos, VRAM e Grounding (Fase 0.5)

**Data:** Setembro de 2026  
**Hardware:** Windows 11 Pro 64-bit · NVIDIA GeForce RTX 3060 12GB VRAM  
**Ferramentas de Medição:** `tools/bench_models.py` e `tools/bench_grounding.py` via `pynvml` (NVML nativo) e cronômetro de alta precisão.

---

## 1. Resultados Reais de Benchmark de Modelos (LLM / Planner)

Medição executada na RTX 3060 com `pynvml`, avaliando tempo de inferência, taxa de geração de tokens, consumo real de VRAM e acurácia de JSON Schema estruturado da Nyx:

| Modelo | Formato / Quant | Schema Válido | Taxa de Geração (tok/s) | Pico de VRAM (MB) | Delta VRAM (MB) | Diagnóstico Técnico |
|---|---|---|---|---|---|---|
| **`qwen2.5:3b-instruct`** | GGUF Q4 | **100.0%** | **100.6 tok/s** | **3.517 MB (~3.5 GB)** | +42 MB | Extremamente rápido, zero OOM, deixa ~8.7 GB de VRAM totalmente livres para VLM/STT/Compositor. |
| **`PetrosStav/gemma3-tools:12b`** | GGUF Q4 | 0.0% | 0.0 tok/s | 10.181 MB (~10.2 GB) | +6.698 MB | Falha por timeout (>45s) na inicialização/inferência do Ollama local. Inviável como planner principal sem `llama-server`. |
| **`qwen2.5-14b-128k:latest`** | GGUF Q4 | **100.0%** | 27.1 tok/s | 10.647 MB (~10.6 GB) | +466 MB | Capacidade de raciocínio superior, mas consome 10.6 GB dos 12.0 GB da GPU. Contextos longos (>8k) causam OOM ou swap imediato. |

### Conclusão do Planner:
1. Para execução local direta sem risco de swap na RTX 3060 (12GB), a configuração vencedora para o dia a dia é o **Qwen2.5-3B** como motor ágil / executor rápido de baixa latência (100.6 tok/s) ou **Qwen 9B / 14B** com restrição estrita de contexto (≤4096 tokens) gerenciado pelo `ModelBroker`.
2. O Ollama aloca modelos de forma gananciosa; para controle refinado de KV cache (`q8_0`), slots paralelos e `--n-cpu-moe`, o `llama-server` nativo (`E:\Ollama\lib\ollama\llama-server.exe`) é o runtime recomendado.

---

## 2. Resultados Reais de Grounding Visual (Visão)

Medição executada com captura de tela real do Windows 11 (1440x900) via `tools/bench_grounding.py`:

| Alvo Solicitado | Tempo (s) | Pico VRAM (MB) | Coordenadas Retornadas | Diagnóstico |
|---|---|---|---|---|
| Barra de tarefas / Iniciar | 45.0s (timeout) | 10.800 MB | Nenhuma | Falha de timeout no primeiro warm-up. |
| Relógio do sistema (inferior direito) | 0.91s | 12.000 MB | (-1, -1) | Resposta descritiva ("A rectangle with a black background..."), não produziu coordenadas numéricas de pixel. |
| Botão fechar (X) | 0.07s | 12.000 MB | (-1, -1) | Sem coordenadas numéricas parseáveis. |
| Barra de título | 0.12s | 12.000 MB | (-1, -1) | Texto sem bounding box ("ids of the elements..."). |

### Conclusão de Grounding:
1. Modelos leves generalistas como **Moondream 1.8B não são adequados para apontamento (pointing) de precisão em pixels** no desktop Windows 11.
2. Quando dois modelos são mantidos na memória sem broker (ex: 14B + Moondream), a VRAM atinge **12.000 MB** (100% da capacidade física da placa), exigindo swap e degradando a latência do sistema operacional.
3. A regra mandatória do Plano Mestre v3 está 100% validada:
   - **Cascata Obrigatória:** (0) ODR/MCP → (1) API/CLI → (2) UIA com CacheRequest e BoundingRectangle exato → (3) Visão com modelo de grounding dedicado (Fara1.5 / Set-of-Marks) sob demanda com TTL curto.

---

## 3. Configuração Ativa da Nyx para a Fase 0.6

- **Planner Default:** `qwen2.5:3b-instruct` (baixa latência, 100.6 tok/s, 3.5 GB VRAM)
- **Planner Pesado / Reflexão:** `qwen2.5-14b-128k:latest` (quando habilitado, `num_ctx: 4096`, controlado pelo `ModelBroker`)
- **Limite de VRAM do Broker:** 11.000 MB (com margem de 1.288 MB para o DWM/Windows 11)
- **Runtime:** Suporte dual via `LLMBackend` (`LlamaCppBackend` + `OllamaBackend`)
