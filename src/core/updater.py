"""Verified GitHub release discovery and staging for the Windows app updater."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app_paths import user_data_dir
from app_version import __version__

OWNER = "Kronos1027"
REPOSITORY = "nyx-agent"
MAX_ARCHIVE_BYTES = 1_000_000_000
MAX_EXPANDED_BYTES = 2_000_000_000
MAX_ARCHIVE_FILES = 10_000
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    page_url: str
    archive_url: str
    checksum_url: str
    archive_name: str
    archive_size: int


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(value)
    if not match:
        raise ValueError(f"Versão inválida na publicação: {value!r}")
    return tuple(int(part) for part in match.groups())


def _read_url(url: str, limit: int, *, timeout: float = 20.0) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"api.github.com", "github.com"}:
        raise ValueError("A atualização apontou para um endereço fora do GitHub seguro.")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Nyx-Desktop-Updater"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_host = urlparse(response.geturl()).hostname
        if final_host not in {"api.github.com", "github.com", "release-assets.githubusercontent.com"}:
            raise ValueError("O download foi redirecionado para um domínio inesperado.")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("O arquivo de atualização excede o limite permitido.")
    return data


def _download_file(url: str, destination: Path, limit: int, *, timeout: float) -> tuple[int, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"api.github.com", "github.com"}:
        raise ValueError("A atualização apontou para um endereço fora do GitHub seguro.")
    request = urllib.request.Request(url, headers={"User-Agent": "Nyx-Desktop-Updater"})
    digest = hashlib.sha256()
    written = 0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_host = urlparse(response.geturl()).hostname
        if final_host not in {"api.github.com", "github.com", "release-assets.githubusercontent.com"}:
            raise ValueError("O download foi redirecionado para um domínio inesperado.")
        with destination.open("wb") as output:
            while block := response.read(1024 * 1024):
                written += len(block)
                if written > limit:
                    raise ValueError("O arquivo de atualização excede o limite permitido.")
                digest.update(block)
                output.write(block)
    return written, digest.hexdigest()


def check_for_update() -> UpdateRelease | None:
    """Return the newest stable release if it is newer than this installation."""
    endpoint = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/releases/latest"
    release = json.loads(_read_url(endpoint, 1_000_000))
    if release.get("draft") or release.get("prerelease"):
        return None
    tag = str(release.get("tag_name", ""))
    version = tag.removeprefix("v")
    if _version_tuple(version) <= _version_tuple(__version__):
        return None

    expected_name = f"Nyx-{version}-windows-x64-portable.zip"
    assets = {asset.get("name"): asset for asset in release.get("assets", [])}
    archive = assets.get(expected_name)
    checksum = assets.get(expected_name + ".sha256")
    if not archive or not checksum:
        raise ValueError("A versão publicada não contém o pacote e o checksum esperados.")
    size = int(archive.get("size", 0))
    if size <= 0 or size > MAX_ARCHIVE_BYTES:
        raise ValueError("O pacote publicado tem tamanho inválido.")
    return UpdateRelease(
        version=version,
        page_url=str(release.get("html_url", "https://github.com/Kronos1027/nyx-agent/releases")),
        archive_url=str(archive.get("browser_download_url", "")),
        checksum_url=str(checksum.get("browser_download_url", "")),
        archive_name=expected_name,
        archive_size=size,
    )


def updater_supported() -> bool:
    if not getattr(sys, "frozen", False):
        return False
    install_root = Path(sys.executable).resolve().parent
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return install_root == (local_app_data / "Programs" / "Nyx").resolve()


def _extract_verified(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    expanded_size = 0
    count = 0
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            count += 1
            if count > MAX_ARCHIVE_FILES:
                raise ValueError("O pacote contém arquivos demais.")
            if "\x00" in info.filename or ":" in info.filename:
                raise ValueError("O pacote contém um nome de arquivo inválido para o Windows.")
            relative = Path(info.filename.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("O pacote contém um caminho de arquivo inválido.")
            target = (destination / relative).resolve()
            if os.path.commonpath((str(root), str(target))) != str(root):
                raise ValueError("O pacote tenta gravar fora da pasta de atualização.")
            # ZIP Unix symlinks can escape the staging folder after extraction.
            mode = info.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise ValueError("Links simbólicos não são aceitos no pacote de atualização.")
            expanded_size += info.file_size
            if expanded_size > MAX_EXPANDED_BYTES:
                raise ValueError("O conteúdo expandido excede o limite permitido.")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)

    if not (destination / "Nyx.exe").is_file():
        raise ValueError("O pacote não contém Nyx.exe na pasta principal.")


def stage_update(release: UpdateRelease) -> Path:
    """Download, SHA-256 verification, and safe extraction. Never changes app files."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Atualização só está disponível no aplicativo instalado.")
    install_root = Path(sys.executable).resolve().parent
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    expected_install = (local_app_data / "Programs" / "Nyx").resolve()
    if install_root != expected_install:
        raise RuntimeError("Atualização automática está disponível na instalação padrão por usuário.")

    checksum_text = _read_url(release.checksum_url, 1024).decode("ascii", errors="strict")
    checksum_match = re.fullmatch(
        rf"\s*([0-9a-fA-F]{{64}})\s+\*?{re.escape(release.archive_name)}\s*\n?",
        checksum_text,
    )
    if not checksum_match:
        raise ValueError("O arquivo SHA256 da publicação está malformado.")
    stage_root = user_data_dir() / "updates" / release.version
    payload = stage_root / "payload"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    try:
        archive_path = stage_root / release.archive_name
        byte_count, digest = _download_file(
            release.archive_url, archive_path, MAX_ARCHIVE_BYTES, timeout=90
        )
        if byte_count != release.archive_size:
            raise ValueError("O tamanho baixado difere do tamanho publicado pelo GitHub.")
        if digest.casefold() != checksum_match.group(1).casefold():
            raise ValueError("O SHA256 do pacote não confere; a atualização foi cancelada.")
        _extract_verified(archive_path, payload)
        archive_path.unlink(missing_ok=True)
    except Exception:
        shutil.rmtree(stage_root, ignore_errors=True)
        raise
    return payload


def launch_staged_update(payload: Path, parent_pid: int, version: str) -> None:
    """Start a detached, rollback-capable per-user update helper."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Atualização só está disponível no aplicativo instalado.")
    if not _VERSION.fullmatch(version):
        raise ValueError("Versão inválida para instalar.")
    install_root = Path(sys.executable).resolve().parent
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    expected_install = (local_app_data / "Programs" / "Nyx").resolve()
    if install_root != expected_install or not (install_root / "Nyx.exe").is_file():
        raise RuntimeError("A Nyx não está na pasta de instalação padrão.")
    payload = payload.resolve()
    if not (payload / "Nyx.exe").is_file():
        raise ValueError("A pasta preparada não contém Nyx.exe.")

    helper = payload.parent / "apply-update.ps1"
    script = r'''param([int]$WaitPid, [string]$InstallRoot, [string]$Payload, [string]$Version)
$ErrorActionPreference = "Stop"
$install = [System.IO.Path]::GetFullPath($InstallRoot)
$parent = [System.IO.Path]::GetFullPath((Split-Path -Parent $install))
if ($install -ne [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs\Nyx"))) { throw "Pasta de instalação não permitida." }
if (-not (Test-Path -LiteralPath (Join-Path $Payload "Nyx.exe") -PathType Leaf)) { throw "Pacote preparado inválido." }
Wait-Process -Id $WaitPid -ErrorAction SilentlyContinue
$ready = Join-Path $parent (".Nyx-update-" + $Version)
$backup = Join-Path $parent "Nyx.previous"
$marker = Join-Path $backup ".nyx-update-backup"
if (Test-Path -LiteralPath $ready) { Remove-Item -LiteralPath $ready -Recurse -Force }
New-Item -ItemType Directory -Path $ready -Force | Out-Null
Get-ChildItem -LiteralPath $Payload -Force | Copy-Item -Destination $ready -Recurse -Force
if (Test-Path -LiteralPath $backup) {
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw "Pasta de rollback não pertence à Nyx; nenhuma cópia foi substituída." }
    Remove-Item -LiteralPath $backup -Recurse -Force
}
Set-Content -LiteralPath (Join-Path $install ".nyx-update-backup") -Value $Version -Encoding ascii
Move-Item -LiteralPath $install -Destination $backup
try {
    Move-Item -LiteralPath $ready -Destination $install
    $env:NYX_SELF_CHECK_REPORT = Join-Path $env:LOCALAPPDATA "Nyx\logs\update-self-check.json"
    & (Join-Path $install "Nyx.exe") --self-check | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Autoteste da versão nova falhou." }
    Start-Process -FilePath (Join-Path $install "Nyx.exe") -WorkingDirectory $install
} catch {
    if (Test-Path -LiteralPath $install) { Remove-Item -LiteralPath $install -Recurse -Force }
    if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $install }
    Remove-Item -LiteralPath (Join-Path $install ".nyx-update-backup") -Force -ErrorAction SilentlyContinue
    throw
} finally {
    Remove-Item Env:\NYX_SELF_CHECK_REPORT -ErrorAction SilentlyContinue
}
'''
    helper.write_text(script, encoding="utf-8")
    import subprocess

    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper),
            "-WaitPid", str(parent_pid), "-InstallRoot", str(install_root),
            "-Payload", str(payload), "-Version", version,
        ],
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
