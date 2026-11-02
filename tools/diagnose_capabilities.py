"""Diagnóstico Windows real; execução explícita, sem modelo ou respostas simuladas.

Por padrão consulta catálogo/recursos. --open-apps abre programas reais;
não fecha janelas, não digita nelas e não modifica perfis pessoais.
Resultados brutos ficam em build; evidência pública omite caminhos e títulos.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.runtime_budget import model_weight_budget_bytes, resource_snapshot, safe_context_tokens  # noqa: E402
from core.verifier import ActionVerifier  # noqa: E402
from tools.installed_apps import resolve_app  # noqa: E402

APPS = ("calculadora", "Bloco de notas", "o navegador", "Chrome", "Edge", "o discord",
        "Spotify", "Steam", "OBS", "VS Code", "Antigravity", "Explorador de Arquivos",
        "Configurações", "WhatsApp", "Paint")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open-apps", action="store_true")
    parser.add_argument("--repeat", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Este diagnóstico exige Windows real.")
    import psutil
    report = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "scope": "ferramentas reais; sem planejador LLM; não é aceite ponta a ponta",
              "opens_apps": args.open_apps, "repetitions": args.repeat, "apps": []}
    snapshot = resource_snapshot()
    report["resources_before"] = asdict(snapshot)
    report["weight_budget_bytes"] = model_weight_budget_bytes(snapshot)
    report["context_tokens"] = safe_context_tokens(snapshot)
    processes = []
    for process in psutil.process_iter(["name", "memory_info"]):
        try:
            processes.append({"name": process.info["name"], "rss_bytes": process.info["memory_info"].rss})
        except (psutil.Error, AttributeError):
            continue
    report["top10_rss"] = sorted(processes, key=lambda p: p["rss_bytes"], reverse=True)[:10]
    for route in ("ps", "tags"):
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/" + route, timeout=5) as response:
                data = json.load(response)
            report["ollama_" + route] = [{k: m.get(k) for k in ("name", "size", "size_vram", "context_length")}
                                        for m in data.get("models", [])]
        except Exception as exc:
            report["ollama_" + route] = {"error": str(exc)}
    ui = browser = None
    raw = []
    try:
        if args.open_apps:
            from tools.ui_tool import UITool
            from tools.browser_tool import BrowserSession
            ui = UITool(screenshots_dir=Path("build/diagnostic/screenshots"))
            browser = BrowserSession(headless=True, persistent_profile=None)
            ui.browser_session = browser
        for name in APPS:
            attempts = []
            for _ in range(args.repeat):
                started = time.perf_counter()
                try:
                    if ui:
                        result = ui.open_app({"app": name})
                        verdict = ActionVerifier().verify("ui_action", {"action": "open_app", "app": name}, result)
                        raw.append({"app": name, "result": asdict(result), "verifier": asdict(verdict)})
                        attempt = {"ok": result.ok, "verified": verdict.verified,
                                   "check": verdict.check_type, "error": result.error,
                                   "window_count": len(result.meta.get("windows", []))}
                    else:
                        app = resolve_app(name)
                        attempt = {"ok": True, "resolved_name": app.name, "source": app.source}
                except Exception as exc:
                    attempt = {"ok": False, "error": str(exc)}
                attempt["elapsed_s"] = round(time.perf_counter() - started, 4)
                attempts.append(attempt)
            report["apps"].append({"name": name, "attempts": attempts,
                                   "median_s": statistics.median(a["elapsed_s"] for a in attempts)})
    finally:
        if browser:
            browser.close()
    report["resources_after"] = asdict(resource_snapshot())
    # Raw errors can contain paths; keep raw output private, publish a reduced copy.
    private = Path("build/diagnostic")
    private.mkdir(parents=True, exist_ok=True)
    (private / (args.output.stem + "-raw.json")).write_text(
        json.dumps({"report": report, "tool_results": raw}, ensure_ascii=False, indent=2), encoding="utf-8")
    for app in report["apps"]:
        for attempt in app["attempts"]:
            if attempt.get("error"):
                error = attempt["error"]
                attempt["error"] = error.replace(str(Path.cwd()), "<projeto>").replace(str(Path.home()), "<usuario>")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cases": len(report["apps"]),
                      "ok": sum(all(a["ok"] for a in item["attempts"]) for item in report["apps"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
