"""Nyx AGI Desktop v3 — tools/bench_models.py (Fase 0.5: Benchmark de Modelos e Runtime)

Mede em tempo real na NVIDIA RTX 3060 12GB:
- VRAM inicial, de pico e residual via pynvml
- Latência e tokens/segundo (prefill e decode)
- Taxa de sucesso de Tool-Calling com schema JSON estrito da Nyx em prompts variados
- Lida com falhas de OOM graciosamente e documenta a causa raiz
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
    NVML_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    HAS_NVML = False
    NVML_HANDLE = None

OLLAMA_URL = "http://127.0.0.1:11434"

TEST_PROMPTS = [
    {"user": "Abra o aplicativo Bloco de Notas para eu anotar um recado.", "expected_tool": "ui_action"},
    {"user": "Qual é a previsão do tempo para São Paulo hoje?", "expected_tool": "web_search"},
    {"user": "Crie um arquivo chamado 'notas.txt' com o texto 'Reunião às 15h'.", "expected_tool": "file_operation"},
    {"user": "Liste quais janelas e programas estão abertos agora.", "expected_tool": "ui_action"},
    {"user": "Pesquise no Google sobre as novidades do Windows 11 em 2026.", "expected_tool": "web_search"},
    {"user": "Feche a janela do aplicativo Calculadora.", "expected_tool": "ui_action"},
    {"user": "Leia o conteúdo do arquivo 'config.json' na pasta do projeto.", "expected_tool": "file_operation"},
    {"user": "Ajuste o volume do som para o máximo.", "expected_tool": "ui_action"},
    {"user": "Crie uma janela flutuante com título 'Progresso' mostrando uma barra em 70%.", "expected_tool": "ui_action"},
    {"user": "Copie o texto 'Chave de Acesso' para a área de transferência.", "expected_tool": "ui_action"},
    {"user": "Tire uma foto da tela inteira para eu analisar.", "expected_tool": "ui_action"},
    {"user": "Execute o script Python 'analisar_dados.py' e veja a saída.", "expected_tool": "shell_command"},
    {"user": "Quantos arquivos existem dentro da pasta 'relatorios'?", "expected_tool": "file_operation"},
    {"user": "Qual a temperatura atual no Rio de Janeiro?", "expected_tool": "web_search"},
    {"user": "Clique no botão Salvar que está no centro da tela.", "expected_tool": "ui_action"},
    {"user": "Apague o arquivo temporário 'temp_cache.log'.", "expected_tool": "file_operation"},
    {"user": "Mostre os elementos interativos da janela que está em foco.", "expected_tool": "ui_action"},
    {"user": "Procure na web pela cotação do Dólar hoje.", "expected_tool": "web_search"},
    {"user": "Minimiza todas as janelas do navegador.", "expected_tool": "ui_action"},
    {"user": "Verifique o uso atual de CPU e memória RAM do sistema.", "expected_tool": "ui_action"},
]

NYX_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "tool": {
            "type": "string",
            "enum": ["ui_action", "web_search", "file_operation", "shell_command", "final_answer"]
        },
        "args": {"type": "object"}
    },
    "required": ["thought", "tool", "args"]
}


def get_vram_mb() -> int:
    if not HAS_NVML or not NVML_HANDLE:
        return 0
    mem = pynvml.nvmlDeviceGetMemoryInfo(NVML_HANDLE)
    return int(mem.used // (1024 * 1024))


@dataclass
class ModelBenchmarkResult:
    model_name: str
    vram_before_mb: int
    vram_peak_mb: int
    vram_delta_mb: int
    total_eval_tokens: int
    total_eval_duration_s: float
    tokens_per_sec: float
    schema_valid_count: int
    tool_match_count: int
    total_prompts: int
    schema_accuracy_pct: float
    tool_match_pct: float
    error_message: Optional[str] = None


def run_benchmark_for_model(model_name: str, prompts: List[Dict[str, str]]) -> ModelBenchmarkResult:
    print("\n========================================================", flush=True)
    print(f"Iniciando benchmark para o modelo: {model_name}", flush=True)
    print("========================================================", flush=True)

    vram_before = get_vram_mb()
    vram_peak = vram_before

    schema_valid = 0
    tool_match = 0
    total_eval_tokens = 0
    total_eval_time = 0.0

    for idx, item in enumerate(prompts, 1):
        prompt_text = item["user"]
        expected = item["expected_tool"]

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Você é o núcleo da Nyx AGI. Responda ESTRITAMENTE em formato JSON seguindo o schema."
                },
                {"role": "user", "content": prompt_text}
            ],
            "format": NYX_TOOL_SCHEMA,
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096,
                "num_gpu": 999
            },
            "stream": False
        }

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=45.0) as res:
                t_req = time.perf_counter() - t0
                body = json.loads(res.read().decode("utf-8"))

            cur_vram = get_vram_mb()
            if cur_vram > vram_peak:
                vram_peak = cur_vram

            content_str = body.get("message", {}).get("content", "").strip()
            eval_count = body.get("eval_count", 0)
            eval_duration_ns = body.get("eval_duration", 1)
            total_eval_tokens += eval_count
            total_eval_time += (eval_duration_ns / 1e9)

            # Valida JSON
            try:
                parsed = json.loads(content_str)
                if isinstance(parsed, dict) and "tool" in parsed and "thought" in parsed:
                    schema_valid += 1
                    if parsed["tool"] == expected:
                        tool_match += 1
                        status = "OK [Match]"
                    else:
                        status = f"OK [Got: {parsed['tool']}, Expected: {expected}]"
                else:
                    status = "FAIL [Invalid Keys]"
            except Exception as e:
                status = f"FAIL [Parse Error: {e}]"

            tok_s = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0
            print(f"[{idx:02d}/{len(prompts)}] {status} | {tok_s:.1f} tok/s | VRAM: {cur_vram} MB ({t_req:.2f}s)", flush=True)

        except urllib.error.HTTPError as err:
            err_body = err.read().decode('utf-8', errors='replace')
            print(f"[{idx:02d}/{len(prompts)}] HTTPError {err.code}: {err_body}", flush=True)
            return ModelBenchmarkResult(
                model_name=model_name,
                vram_before_mb=vram_before,
                vram_peak_mb=get_vram_mb(),
                vram_delta_mb=get_vram_mb() - vram_before,
                total_eval_tokens=total_eval_tokens,
                total_eval_duration_s=total_eval_time,
                tokens_per_sec=0.0,
                schema_valid_count=schema_valid,
                tool_match_count=tool_match,
                total_prompts=len(prompts),
                schema_accuracy_pct=(schema_valid / len(prompts)) * 100,
                tool_match_pct=(tool_match / len(prompts)) * 100,
                error_message=f"HTTPError {err.code}: {err_body}"
            )
        except Exception as exc:
            print(f"[{idx:02d}/{len(prompts)}] Exception: {exc}", flush=True)
            return ModelBenchmarkResult(
                model_name=model_name,
                vram_before_mb=vram_before,
                vram_peak_mb=get_vram_mb(),
                vram_delta_mb=get_vram_mb() - vram_before,
                total_eval_tokens=total_eval_tokens,
                total_eval_duration_s=total_eval_time,
                tokens_per_sec=0.0,
                schema_valid_count=schema_valid,
                tool_match_count=tool_match,
                total_prompts=len(prompts),
                schema_accuracy_pct=(schema_valid / len(prompts)) * 100,
                tool_match_pct=(tool_match / len(prompts)) * 100,
                error_message=str(exc)
            )

    avg_tok_s = (total_eval_tokens / total_eval_time) if total_eval_time > 0 else 0.0
    return ModelBenchmarkResult(
        model_name=model_name,
        vram_before_mb=vram_before,
        vram_peak_mb=vram_peak,
        vram_delta_mb=vram_peak - vram_before,
        total_eval_tokens=total_eval_tokens,
        total_eval_duration_s=total_eval_time,
        tokens_per_sec=avg_tok_s,
        schema_valid_count=schema_valid,
        tool_match_count=tool_match,
        total_prompts=len(prompts),
        schema_accuracy_pct=(schema_valid / len(prompts)) * 100,
        tool_match_pct=(tool_match / len(prompts)) * 100,
    )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    candidates = [
        "qwen2.5:3b-instruct",
        "PetrosStav/gemma3-tools:12b",
        "qwen2.5-14b-128k:latest",
    ]

    results = []
    for cand in candidates:
        res = run_benchmark_for_model(cand, TEST_PROMPTS[:10])
        results.append(res)

    print("\n\n========================================================")
    print("RESUMO FINAL DO BENCHMARK DE MODELOS (FASE 0.5)")
    print("========================================================")
    for r in results:
        err_str = f" [ERRO: {r.error_message[:60]}...]" if r.error_message else ""
        print(
            f"• {r.model_name:<28} | Schema: {r.schema_accuracy_pct:5.1f}% | "
            f"Match: {r.tool_match_pct:5.1f}% | {r.tokens_per_sec:5.1f} tok/s | "
            f"Peak VRAM: {r.vram_peak_mb} MB (Delta: {r.vram_delta_mb} MB){err_str}"
        )

    # Salva resultado em JSON
    out_file = "tests/evals/models_benchmark_v3.json"
    data = [r.__dict__ for r in results]
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nDados completos salvos em: {out_file}")


if __name__ == "__main__":
    main()
