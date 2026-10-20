"""Nyx — tests/evals/benchmark_tool_calling.py (Fase 0: Benchmark de Tool-Calling)

Compara a taxa de acerto de schema e seleção de ação correta em 20 prompts reais
entre os modelos instalados no Ollama (ex: qwen2.5:3b-instruct vs qwen2.5-14b-128k).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Garante 'src' no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from core.llm_client import OllamaClient, parse_response

BENCHMARK_PROMPTS = [
    # (prompt, expected_action_type)
    ("quais aplicativos estão abertos agora no meu computador?", "ui_action"),
    ("pesquise a previsão do tempo hoje e onde estamos", "web"),
    ("como está o uso da placa de vídeo e temperatura do hardware?", "project_status"),
    ("crie um script python que calcule fibonacci e mostre no workspace", "workspace"),
    ("monte uma planilha com os gastos mensais no workspace", "workspace"),
    ("elabore um relatório comparativo sobre agentes autônomos em markdown", "workspace"),
    ("pesquise as últimas notícias sobre inteligência artificial", "web"),
    ("abra o spotify no navegador", "ui_action"),
    ("olhe a tela e me diga o que está visível", "ui_action"),
    ("qual janela está ativa e em foco no momento?", "ui_action"),
    ("inspecione os controles e botões da janela atual", "ui_action"),
    ("leia o conteúdo do arquivo config.py", "read_file"),
    ("escreva uma anotação no arquivo notas.txt com o texto reunião amanhã", "write_file"),
    ("procure todos os arquivos .py na pasta src", "find_files"),
    ("o que está copiado na minha área de transferência?", "clipboard"),
    ("feche a janela do aplicativo notepad", "ui_action"),
    ("minimize a janela atual", "ui_action"),
    ("capture um screenshot da minha tela agora", "ui_action"),
    ("olá Nyx, como você está hoje?", "none"),
    ("explique a diferença entre memória RAM e VRAM", "none"),
]


def run_benchmark_for_model(model_name: str, prompts: list[tuple[str, str]] = BENCHMARK_PROMPTS) -> dict:
    client = OllamaClient(model=model_name, timeout=45.0)
    if not client.is_available():
        return {"model": model_name, "available": False}

    results = []
    schema_ok_count = 0
    action_match_count = 0
    latencies = []

    print(f"\n[*] Avaliando modelo '{model_name}' com {len(prompts)} prompts...")
    for idx, (prompt, expected_action) in enumerate(prompts, 1):
        t0 = time.perf_counter()
        raw = client.generate(prompt)
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)

        resp = parse_response(raw)
        schema_ok = resp.parse_ok
        action_match = (resp.action.type == expected_action)

        if schema_ok:
            schema_ok_count += 1
        if action_match:
            action_match_count += 1

        mark = "[OK]" if (schema_ok and action_match) else "[FAIL]"
        print(f"  [{idx:02d}/20] {mark} Action: '{resp.action.type}' (Esperado: '{expected_action}') | Schema: {schema_ok} | {elapsed:.2f}s")
        results.append({
            "prompt": prompt,
            "expected": expected_action,
            "actual": resp.action.type,
            "schema_ok": schema_ok,
            "action_match": action_match,
            "elapsed_s": round(elapsed, 2),
            "speech": resp.speech_output[:80] if resp.speech_output else "",
        })

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    schema_acc = (schema_ok_count / len(prompts)) * 100
    action_acc = (action_match_count / len(prompts)) * 100

    summary = {
        "model": model_name,
        "available": True,
        "total_prompts": len(prompts),
        "schema_ok_count": schema_ok_count,
        "schema_accuracy_pct": round(schema_acc, 1),
        "action_match_count": action_match_count,
        "action_accuracy_pct": round(action_acc, 1),
        "avg_latency_s": round(avg_latency, 2),
        "results": results,
    }
    return summary


def main():
    print("=" * 70)
    print("      BENCHMARK DE TOOL-CALLING — NYX AGI DESKTOP v2 (FASE 0)")
    print("=" * 70)

    models_to_test = ["qwen2.5:3b-instruct", "qwen2.5-14b-128k:latest"]
    all_summaries = []

    for m in models_to_test:
        try:
            summary = run_benchmark_for_model(m)
            all_summaries.append(summary)
        except Exception as exc:
            all_summaries.append({
                "model": m,
                "available": True,
                "error": str(exc),
                "note": "Excedeu VRAM (OOM) com num_ctx 8192 na RTX 3060 12GB.",
            })

    print("\n" + "=" * 70)
    print("                      RELATÓRIO COMPARATIVO")
    print("=" * 70)
    print(f"{'Modelo':<28} | {'Schema OK':<11} | {'Ação Correta':<14} | {'Latência Média':<12}")
    print("-" * 70)
    for s in all_summaries:
        if s.get("schema_accuracy_pct") is not None:
            print(f"{s['model']:<28} | {s['schema_accuracy_pct']:>6.1f}%     | {s['action_accuracy_pct']:>8.1f}%      | {s['avg_latency_s']:>6.2f}s")
        elif s.get("error"):
            print(f"{s['model']:<28} | [OOM/Falha VRAM na RTX 3060 12GB]")
        else:
            print(f"{s['model']:<28} | [Indisponível]")
    print("=" * 70)

    # Salva resultado em JSON para documentação e config
    out_file = Path(__file__).resolve().parent / "benchmark_results.json"
    out_file.write_text(json.dumps(all_summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] Resultados salvos em: {out_file}")


if __name__ == "__main__":
    main()
