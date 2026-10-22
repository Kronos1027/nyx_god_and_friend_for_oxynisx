"""Start an installed local Ollama safely when no server is listening."""

from __future__ import annotations

import json
import errno
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from app_paths import user_data_dir

_owned_process: subprocess.Popen | None = None


def runtime_config_path() -> Path:
    return user_data_dir() / "data" / "runtime.json"


def load_runtime_config() -> dict[str, str]:
    path = runtime_config_path()
    try:
        candidates = [p for p in path.parent.glob("runtime-settings-*.json")
                      if re.fullmatch(r"runtime-settings-[0-9a-f]{32}\.json", p.name) and not p.is_symlink()]
        if path.is_file():
            candidates.append(path)
        candidates.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
    except OSError:
        candidates = [path]
    for candidate in candidates:
        try:
            if candidate.stat().st_size > 16_384:
                continue
            value = json.loads(candidate.read_text(encoding="utf-8"))
            keys = ("ollama_executable", "models_directory", "preferred_model")
            if not isinstance(value, dict) or not any(key in value for key in keys):
                continue
            if any(not isinstance(value.get(key, ""), str) for key in keys):
                continue
            return {key: value.get(key, "") for key in keys}
        except (OSError, ValueError):
            continue
    return {}


def save_runtime_config(executable: str, models_directory: str, preferred_model: str | None = None) -> None:
    if preferred_model is None:
        preferred_model = load_runtime_config().get("preferred_model", "")
    preferred_model = preferred_model.strip()
    if preferred_model and (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", preferred_model)
                            or preferred_model.lower().endswith("cloud")):
        raise ValueError("Informe o nome exato de um modelo local, por exemplo qwen3.5:4b.")
    if executable:
        binary = Path(executable).expanduser().resolve()
        if not binary.is_file() or binary.name.casefold() not in {"ollama.exe", "ollama"}:
            raise ValueError("Selecione o executável Ollama instalado.")
        executable = str(binary)
    if models_directory:
        models = Path(models_directory).expanduser().resolve()
        if not models.is_dir():
            raise ValueError("A pasta de modelos não existe.")
        models_directory = str(models)
    path = runtime_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"ollama_executable": executable, "models_directory": models_directory,
                                     "preferred_model": preferred_model}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.replace(path)
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
            raise
        # Immutable alternate record preserves the previous valid settings if interrupted.
        alternate = path.with_name(f"runtime-settings-{uuid4().hex}.json")
        with alternate.open("xb") as stream:
            stream.write(temporary.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        records = sorted((p for p in path.parent.glob("runtime-settings-*.json")
                          if re.fullmatch(r"runtime-settings-[0-9a-f]{32}\.json", p.name) and not p.is_symlink()),
                         key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for old in records[5:]:
            if old != alternate:
                try:
                    old.unlink()
                except OSError:
                    pass


@dataclass(frozen=True)
class OllamaServiceState:
    ready: bool
    started_by_nyx: bool
    reason: str
    pid: int | None = None


def _healthy(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/version", timeout=0.5) as response:
            return response.status == 200
    except Exception:
        return False


def ensure_local_ollama(timeout: float = 8.0) -> OllamaServiceState:
    global _owned_process
    host = os.environ.get("NYX_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if _healthy(host):
        owned = _owned_process is not None and _owned_process.poll() is None
        return OllamaServiceState(True, owned, "Ollama disponível.", _owned_process.pid if owned else None)
    try:
        parsed = urlparse(host)
        port = parsed.port or 11434
    except ValueError:
        return OllamaServiceState(False, False, "O endereço configurado para Ollama é inválido.")
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return OllamaServiceState(False, False, "O endpoint configurado não respondeu; apenas o Ollama local pode ser iniciado pela Nyx.")
    try:
        with socket.create_connection((parsed.hostname, port), timeout=0.2):
            return OllamaServiceState(False, False, "A porta configurada está ocupada por um serviço que não respondeu como Ollama.")
    except OSError:
        pass

    if _owned_process is None or _owned_process.poll() is not None:
        config = load_runtime_config()
        executable = config.get("ollama_executable") or os.environ.get("NYX_OLLAMA_EXECUTABLE") or shutil.which("ollama")
        if not executable or not Path(executable).is_file():
            return OllamaServiceState(False, False, "Ollama não encontrado. Selecione a instalação em Personalizar.")
        if config.get("models_directory") and not Path(config["models_directory"]).is_dir():
            return OllamaServiceState(False, False, "A pasta de modelos configurada não existe mais. Atualize o caminho em Personalizar.")
        environment = dict(os.environ)
        environment.update({
            "OLLAMA_HOST": f"127.0.0.1:{port}",
            "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_QUEUE": "8", "OLLAMA_KEEP_ALIVE": "5m",
            "OLLAMA_NO_CLOUD": "1", "OLLAMA_FLASH_ATTENTION": "1",
        })
        if config.get("models_directory"):
            environment["OLLAMA_MODELS"] = config["models_directory"]
        log_dir = user_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            with (log_dir / "ollama-service.log").open("ab") as output:
                _owned_process = subprocess.Popen(
                    [executable, "serve"], env=environment,
                    stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True,
                )
        except OSError as exc:
            return OllamaServiceState(False, False, f"Não foi possível iniciar Ollama: {exc}")
    deadline = time.monotonic() + max(0, timeout)
    while time.monotonic() < deadline:
        if _healthy(host):
            return OllamaServiceState(True, True, "Ollama iniciado com limites de carga e conexão somente local.", _owned_process.pid)
        if _owned_process.poll() is not None:
            return OllamaServiceState(False, True, "Ollama terminou durante a inicialização; veja logs/ollama-service.log.", _owned_process.pid)
        time.sleep(0.15)
    return OllamaServiceState(False, True, "Ollama continua iniciando; aguarde e tente novamente.", _owned_process.pid)
