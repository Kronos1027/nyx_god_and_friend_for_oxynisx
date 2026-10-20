"""Nyx — tools/check_gpu.py (Fase 0: Diagnóstico e Validação da GPU RTX 3060)

Executa:
1. `nvidia-smi` para obter nome da GPU, VRAM total/usada, temperatura e utilização.
2. `ollama ps` para verificar se os modelos estão 100% carregados na GPU (CUDA).
3. Requisição de benchmark ao Ollama com options `num_gpu: 999` e `num_ctx: 8192`.
4. Mede e imprime: SIZE, PROCESSOR (100% GPU vs CPU), latência e tokens/segundo (tok/s).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def run_cmd(cmd: str) -> str:
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return res.stdout.strip()
    except Exception as exc:
        return f"Erro ao executar '{cmd}': {exc}"


def check_nvidia_smi() -> dict[str, str]:
    out = run_cmd("nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu --format=csv,noheader,nounits")
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines or "Erro" in out:
        return {"error": out}
    parts = [p.strip() for p in lines[0].split(",")]
    if len(parts) >= 6:
        return {
            "name": parts[0],
            "total_vram_mb": parts[1],
            "used_vram_mb": parts[2],
            "free_vram_mb": parts[3],
            "temp_c": parts[4],
            "utilization_pct": parts[5],
        }
    return {"raw": out}


def check_ollama_ps(ollama_bin: str = "E:\\Ollama\\ollama.exe") -> list[dict[str, str]]:
    cmd = f'"{ollama_bin}" ps' if Path(ollama_bin).exists() else "ollama ps"
    out = run_cmd(cmd)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return []
    models = []
    for ln in lines[1:]:
        parts = ln.split()
        if len(parts) >= 5:
            # Ex: qwen2.5:3b-instruct 357c53fb659c 3.2 GB 100% GPU 29 minutes from now
            models.append({
                "name": parts[0],
                "size": parts[2] + " " + parts[3] if len(parts) > 3 else parts[2],
                "processor": " ".join([p for p in parts if "GPU" in p or "CPU" in p] or ["Desconhecido"]),
                "raw": ln,
            })
    return models


def benchmark_inference(model: str = "qwen2.5:3b-instruct", num_ctx: int = 8192) -> dict:
    url = "http://127.0.0.1:11434/api/generate"
    prompt = "Responda em formato JSON com reasoning, action e speech_output: qual a capital da França?"
    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "options": {
            "num_gpu": 999,
            "num_ctx": num_ctx,
            "temperature": 0.2,
        },
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.perf_counter() - t0
        eval_count = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 1)
        tok_s = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else 0.0
        return {
            "ok": True,
            "elapsed_s": round(elapsed, 3),
            "eval_count": eval_count,
            "tokens_per_second": round(tok_s, 2),
            "response": data.get("response", "").strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def main() -> int:
    print("=" * 65)
    print("         NYX AGI DESKTOP v2 — FASE 0: VERIFICAÇÃO DE GPU")
    print("=" * 65)

    # 1. NVIDIA-SMI
    gpu = check_nvidia_smi()
    if "error" in gpu:
        print(f"[-] Falha ao consultar nvidia-smi: {gpu['error']}")
    else:
        print(f"[+] GPU Detectada: {gpu.get('name', 'Desconhecida')}")
        print(f"    VRAM Total: {gpu.get('total_vram_mb', '?')} MB | Usada: {gpu.get('used_vram_mb', '?')} MB | Livre: {gpu.get('free_vram_mb', '?')} MB")
        print(f"    Temperatura: {gpu.get('temp_c', '?')}°C | Utilização: {gpu.get('utilization_pct', '?')}%")

    print("-" * 65)

    # 2. Benchmark de Inferência com num_gpu: 999 e num_ctx: 8192
    model_name = "qwen2.5:3b-instruct"
    print(f"[*] Executando inferência de teste com '{model_name}' (num_ctx: 8192, num_gpu: 999)...")
    bench = benchmark_inference(model=model_name, num_ctx=8192)
    if not bench.get("ok"):
        print(f"[-] Erro na inferência: {bench.get('error')}")
    else:
        print(f"[+] Inferência concluída com sucesso em {bench['elapsed_s']}s!")
        print(f"    Tokens gerados: {bench['eval_count']} tokens")
        print(f"    Taxa de geração: {bench['tokens_per_second']} tok/s")

    print("-" * 65)

    # 3. OLLAMA PS
    ps_models = check_ollama_ps()
    if not ps_models:
        print("[-] Nenhum modelo reportado em 'ollama ps' (ou serviço reiniciando).")
    else:
        print("[+] Modelos carregados na memória pelo Ollama:")
        for m in ps_models:
            proc = m.get("processor", "")
            is_100_gpu = "100% GPU" in proc or "GPU" in proc
            tag = "[CUDA 100% GPU]" if is_100_gpu else "[CPU/MISTO]"
            print(f"    • Modelo: {m['name']} | Tamanho: {m['size']} | Processador: {proc} {tag}")

    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
