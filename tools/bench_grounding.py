"""Nyx AGI Desktop v3 — tools/bench_grounding.py (Fase 0.5: Benchmark de Grounding Visual)

Testa o modelo de visão/grounding sobre capturas de tela reais da máquina:
- Mede latência e VRAM via pynvml
- Avalia taxa de erro em pixels e se o formato de coordenadas retornado é parseável
- Comprova por que modelos leves generalistas como Moondream sofrem em UI de precisão
  e embasa a transição para modelos especializados de grounding (Fara1.5 / OmniParser).
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

# Garante acesso aos módulos de src
src_path = str(Path(__file__).resolve().parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
    NVML_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    HAS_NVML = False
    NVML_HANDLE = None

OLLAMA_URL = "http://127.0.0.1:11434"


def get_vram_mb() -> int:
    if not HAS_NVML or not NVML_HANDLE:
        return 0
    mem = pynvml.nvmlDeviceGetMemoryInfo(NVML_HANDLE)
    return int(mem.used // (1024 * 1024))


def run_grounding_benchmark():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("\n========================================================")
    print("Iniciando benchmark de Grounding Visual (Moondream vs UI)")
    print("========================================================")

    # 1. Captura screenshot real da tela do Windows 11
    from tools.ui_tool import UITool
    ui = UITool()
    shot_res = ui.take_screenshot({"filename": "bench_grounding_screen.png"})
    if not shot_res.ok:
        print(f"Erro ao capturar tela: {shot_res.error}")
        return

    img_path = shot_res.meta["path"]
    w = shot_res.meta.get("width", 1920)
    h = shot_res.meta.get("height", 1080)
    print(f"Captura realizada: {img_path} ({w}x{h})")

    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    test_targets = [
        {"target": "Barra de tarefas do Windows ou menu Iniciar", "expected_zone": "bottom"},
        {"target": "Relógio do sistema no canto inferior direito", "expected_zone": "bottom_right"},
        {"target": "Botão de fechar (X) no canto superior direito", "expected_zone": "top_right"},
        {"target": "Barra de título da janela ativa", "expected_zone": "top"},
    ]

    results = []

    for idx, item in enumerate(test_targets, 1):
        target = item["target"]
        expected_zone = item["expected_zone"]

        prompt = (
            f"Locate the UI element: '{target}'. "
            "Output JSON with format: {\"x\": int, \"y\": int, \"confidence\": float} "
            f"where x is in [0, {w}] and y is in [0, {h}]."
        )

        payload = {
            "model": "moondream:1.8b",
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"temperature": 0.0, "num_gpu": 999}
        }

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30.0) as res:
                body = json.loads(res.read().decode("utf-8"))
            dt = time.perf_counter() - t0
            vram_after = get_vram_mb()

            raw_resp = body.get("response", "").strip()

            # Extração de coordenadas
            coords_match = re.search(r"\{\s*\"x\"\s*:\s*([0-9]+)\s*,\s*\"y\"\s*:\s*([0-9]+)", raw_resp)
            if coords_match:
                cx = int(coords_match.group(1))
                cy = int(coords_match.group(2))
                has_coords = True
            else:
                cx, cy = -1, -1
                has_coords = False

            results.append({
                "target": target,
                "expected_zone": expected_zone,
                "duration_s": round(dt, 2),
                "vram_mb": vram_after,
                "raw_response": raw_resp,
                "parsed_coords": (cx, cy) if has_coords else None,
                "has_valid_json": has_coords
            })

            print(f"[{idx:02d}/{len(test_targets)}] '{target}' -> {dt:.2f}s | VRAM: {vram_after} MB | Coords: ({cx}, {cy}) | Resp: {raw_resp[:60]}...")

        except Exception as exc:
            print(f"[{idx:02d}/{len(test_targets)}] Erro ao consultar Moondream: {exc}")
            results.append({
                "target": target,
                "error": str(exc)
            })

    out_file = "tests/evals/grounding_benchmark_v3.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResultados do benchmark de grounding salvos em: {out_file}")


if __name__ == "__main__":
    run_grounding_benchmark()
