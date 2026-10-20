"""Stable resource and writable-data paths for development and frozen builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Use the repository while developing and per-user AppData after install."""
    if not is_frozen():
        return project_root()
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "Nyx"


def resource_path(relative_path: str | Path) -> Path:
    """Resolve immutable files bundled by PyInstaller or present in the repo."""
    bundle_root = Path(getattr(sys, "_MEIPASS", project_root()))
    return bundle_root / relative_path


def activate_runtime() -> Path:
    """Move relative runtime databases/logs to the writable per-user directory."""
    data_dir = user_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("data", "logs", "macros", "models"):
        (data_dir / name).mkdir(parents=True, exist_ok=True)
    os.chdir(data_dir)
    return data_dir
