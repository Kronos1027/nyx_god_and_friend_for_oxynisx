"""Offline installation diagnostics used by builds and support reports."""

from __future__ import annotations

import importlib
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app_paths import resource_path, user_data_dir
from app_version import __version__


REQUIRED_MODULES = (
    "PyQt6.QtCore",
    "PyQt6.QtWidgets",
    "faster_whisper",
    "kokoro_onnx",
    "llama_cpp",
    "onnxruntime",
    "sounddevice",
    "soundfile",
    "pywinauto",
    "pyautogui",
)


def run_self_check() -> dict:
    report = {
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "user_data_dir": str(user_data_dir()),
        "checks": {},
    }
    schema = resource_path("src/core/schema.gbnf")
    report["checks"]["schema_resource"] = {"ok": schema.is_file(), "path": str(schema)}

    for module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
            report["checks"][f"module:{module_name}"] = {
                "ok": True,
                "version": getattr(module, "__version__", None),
            }
        except Exception as exc:
            report["checks"][f"module:{module_name}"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    try:
        from core.backup import BackupVault

        with tempfile.TemporaryDirectory(prefix="nyx-backup-check-") as folder:
            vault = BackupVault(Path(folder))
            snapshot = vault.create()
            manifest = vault.inspect(snapshot, vault.key_path.read_bytes())
            report["checks"]["encrypted_backup"] = {"ok": manifest["schema_version"] == 1}
    except Exception as exc:
        report["checks"]["encrypted_backup"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    pet = resource_path("assets/oxynisx/spritesheet.png")
    report["checks"]["companion_resource"] = {"ok": pet.is_file()}

    try:
        from audit.logger import AuditLogger
        from core.agent_loop import AgentLoop
        from core.llm_client import OfflineLLM
        from core.task_runner import TaskRunner
        from tools.registry import ToolRegistry, ToolResult, ToolSpec

        with tempfile.TemporaryDirectory(prefix="nyx-task-check-") as folder:
            root = Path(folder)
            paths = [root / "a.txt", root / "b.txt"]
            llm = OfflineLLM()
            for index, path in enumerate(paths):
                path.write_text(str(index + 1), encoding="utf-8")
            for path in [*paths, None]:
                llm.queue(json.dumps({"reasoning": "self-check", "alternative_suggestion": None,
                                     "emotion": "talk", "action": {"type": "read_file" if path else "none", "params": {"path": str(path)} if path else {}},
                                     "requires_confirmation": False, "confirmation_prompt": None, "speech_output": "self-check"}))
            registry = ToolRegistry()
            registry.register(ToolSpec("read_file", "self-check"), lambda p: ToolResult(True, Path(p["path"]).read_text(encoding="utf-8")))
            runner = TaskRunner(AgentLoop(llm, registry, AuditLogger(root / "logs", session_id="self-check")))
            runner.start("Read two fixture files")
            report["checks"]["multi_step_task"] = {"ok": [s["output"] for s in runner.steps] == ["1", "2"] and not runner.active,
                                                     "planner": "scripted", "actions": len(runner.steps)}
    except Exception as exc:
        report["checks"]["multi_step_task"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        report["checks"]["qt_application"] = {"ok": app is not None}
    except Exception as exc:
        report["checks"]["qt_application"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if report["checks"].get("qt_application", {}).get("ok"):
        window = None
        try:
            from PyQt6.QtCore import QSettings, Qt
            from ui.chat_store import ChatStore
            from ui.desktop import DesktopWindow
            from ui.overlay import OverlayWindow

            with tempfile.TemporaryDirectory(prefix="nyx-desktop-check-") as temporary:
                temporary_path = Path(temporary)
                settings = QSettings(str(temporary_path / "desktop.ini"), QSettings.Format.IniFormat)
                settings.setValue("speech", False)
                settings.setValue("motion", False)
                window = DesktopWindow(
                    OverlayWindow(), ChatStore(temporary_path / "chats.db"), settings
                )
                window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
                window.show()
                app.processEvents()
                preview = window.grab()
                report["checks"]["desktop_render"] = {
                    "ok": not preview.isNull(),
                    "width": preview.width(),
                    "height": preview.height(),
                }
                window.close()
                app.processEvents()
        except Exception as exc:
            if window is not None:
                window.close()
            report["checks"]["desktop_render"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    data_dir = user_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".nyx-check-", delete=True):
            pass
        report["checks"]["writable_user_data"] = {"ok": True}
    except Exception as exc:
        report["checks"]["writable_user_data"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    report["ok"] = all(item.get("ok", False) for item in report["checks"].values())
    report_path = Path(os.environ.get(
        "NYX_SELF_CHECK_REPORT", data_dir / "logs" / "self_check_latest.json"
    ))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
