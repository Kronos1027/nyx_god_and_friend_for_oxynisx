"""Nyx — tools/project_watch_tool.py (Fase 6: Produtividade & Monitor do Ecossistema)

Monitoramento em tempo real do sistema:
- Uso de memória RAM e CPU via psutil.
- Uso de VRAM e temperatura da GPU (NVIDIA RTX 3060) via nvidia-smi.
- Espaço em disco.
- Status do Git dos projetos monitorados.
"""

from __future__ import annotations

import logging
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from tools.registry import ToolResult

log = logging.getLogger(__name__)


class ProjectWatchTool:
    """Monitor de recursos de hardware e repositórios locais."""

    def __init__(self, monitored_roots: list[Path] | None = None) -> None:
        self.monitored_roots = monitored_roots or [Path.cwd()]

    @staticmethod
    def _get_ollama_status() -> tuple[str, dict]:
        """Reports whether a local model is loaded and where its weights reside."""
        try:
            host = os.environ.get("NYX_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
            req = urllib.request.Request(f"{host}/api/ps", method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as response:
                models = json.loads(response.read().decode("utf-8")).get("models", [])
        except Exception:
            return "Ollama local: API indisponível", {"available": False, "models": []}

        if not models:
            return "Ollama local: nenhum modelo carregado", {"available": True, "models": []}

        entries = []
        telemetry = []
        for model in models:
            size = int(model.get("size", 0) or 0)
            vram = int(model.get("size_vram", 0) or 0)
            placement = "CPU" if vram == 0 else "GPU" if size and vram >= size else "GPU parcial"
            name = str(model.get("name") or model.get("model") or "modelo")
            entries.append(f"{name} ({placement})")
            telemetry.append({"name": name, "size_bytes": size, "vram_bytes": vram, "placement": placement})
        return "Ollama local: " + ", ".join(entries), {"available": True, "models": telemetry}

    def get_hardware_status(self, params: dict | None = None) -> ToolResult:
        """Coleta uso de CPU, RAM física e VRAM da GPU NVIDIA."""
        import psutil

        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        total_ram_gb = round(mem.total / (1024**3), 1)
        used_ram_gb = round(mem.used / (1024**3), 1)
        ram_pct = mem.percent

        # GPU VRAM query via nvidia-smi
        vram_info = "NVIDIA GPU: indisponível ou driver ausente"
        gpu_meta = {}
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                parts = [p.strip() for p in proc.stdout.strip().split(",")]
                if len(parts) >= 6:
                    gpu_name = parts[0]
                    vram_total_mb = int(parts[1])
                    vram_used_mb = int(parts[2])
                    _vram_free_mb = int(parts[3])  # noqa: F841
                    gpu_temp = parts[4]
                    gpu_util = parts[5]
                    vram_pct = round((vram_used_mb / vram_total_mb) * 100, 1)
                    vram_info = (
                        f"GPU: {gpu_name} | VRAM: {vram_used_mb}MB / {vram_total_mb}MB "
                        f"({vram_pct}%) | Temp: {gpu_temp}°C | Util: {gpu_util}%"
                    )
                    gpu_meta = {
                        "name": gpu_name,
                        "vram_used_mb": vram_used_mb,
                        "vram_total_mb": vram_total_mb,
                        "vram_pct": vram_pct,
                        "temp_c": gpu_temp,
                    }
        except Exception:
            pass

        # Disco
        disk = shutil.disk_usage(Path.cwd().anchor)
        disk_total_gb = round(disk.total / (1024**3), 1)
        disk_free_gb = round(disk.free / (1024**3), 1)
        disk_pct = round(((disk.total - disk.free) / disk.total) * 100, 1)

        summary = (
            f"Hardware em tempo real:\n"
            f"- CPU: {cpu_pct}%\n"
            f"- RAM: {used_ram_gb}GB / {total_ram_gb}GB ({ram_pct}%)\n"
            f"- {vram_info}\n"
            f"- Disco ({Path.cwd().anchor}): {disk_free_gb}GB livres de {disk_total_gb}GB ({disk_pct}% usado)"
        )

        suggestion = None
        if ram_pct > 85.0:
            suggestion = "RAM alta (>85%): recomendo fechar abas do navegador ou liberar processos inativos."
        elif gpu_meta.get("vram_pct", 0) > 90.0:
            suggestion = "VRAM alta (>90%): consumo de GPU próximo do limite de 12GB."

        if suggestion:
            summary += f"\n\n[Alerta] {suggestion}"

        ollama_summary, ollama_meta = self._get_ollama_status()
        summary += f"\n- {ollama_summary}"

        return ToolResult(
            ok=True,
            output=summary,
            meta={
                "cpu_percent": cpu_pct,
                "ram_percent": ram_pct,
                "ram_used_gb": used_ram_gb,
                "ram_total_gb": total_ram_gb,
                "gpu": gpu_meta,
                "ollama": ollama_meta,
            },
        )

    def get_git_status(self, params: dict) -> ToolResult:
        """Verifica o status git de um repositório."""
        repo_path_raw = params.get("path", str(Path.cwd()))
        repo_path = Path(repo_path_raw).resolve()

        if not (repo_path / ".git").exists():
            return ToolResult(
                ok=False, error=f"O diretório '{repo_path}' não é um repositório git."
            )

        try:
            cmd = ["git", "-C", str(repo_path), "status", "-s", "-b"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8, check=False)
            if proc.returncode != 0:
                return ToolResult(ok=False, error=f"git status falhou: {proc.stderr}")

            output = proc.stdout.strip() or "Repositório limpo, sem alterações pendentes."
            return ToolResult(
                ok=True,
                output=f"Git status ({repo_path.name}):\n{output}",
                meta={"path": str(repo_path), "status": output},
            )
        except Exception as exc:
            return ToolResult(ok=False, error=f"Erro ao consultar git: {exc}")

    def run(self, params: dict) -> ToolResult:
        """Despacha chamada da ferramenta 'project_status'."""
        action = str(params.get("action", params.get("type", "hardware"))).lower()
        if "git" in action or "repo" in action:
            return self.get_git_status(params)
        return self.get_hardware_status(params)


def make_project_watch_tool_func(tool: ProjectWatchTool):
    """Fábrica para ação 'project_status' do registry."""

    def _run(params: dict) -> ToolResult:
        return tool.run(params)

    return _run
