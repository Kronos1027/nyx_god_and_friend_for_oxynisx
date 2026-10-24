"""Nyx — tests/test_new_tools.py

Testes unitários e de integração para as novas ferramentas e componentes:
- UITool
- ClipboardTool
- ProjectWatchTool
- SpriteRenderer
- SpeechToText (Wake word)
- PermissionDialog
"""

import sys
from pathlib import Path

# Garante path para src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tools.clipboard_tool import ClipboardTool
from tools.project_watch_tool import ProjectWatchTool
from tools.ui_tool import UITool
from ui.sprite_renderer import SpriteRenderer
from audio.stt import SpeechToText
from config import NyxConfig
from cli import build_registry


def test_clipboard_tool_operations(monkeypatch):
    import sys

    class MemoryClipboard:
        text = ""

        @classmethod
        def copy(cls, text):
            cls.text = text

        @classmethod
        def paste(cls):
            return cls.text

    monkeypatch.setitem(sys.modules, "pyperclip", MemoryClipboard)
    tool = ClipboardTool(max_history=5)

    # Escrita
    res_write = tool.write_clipboard({"text": "Hello Nyx"})
    assert res_write.ok is True
    assert "Hello Nyx" in res_write.output

    # Leitura
    res_read = tool.read_clipboard()
    assert res_read.ok is True
    assert res_read.output == "Hello Nyx"

    # Histórico
    res_hist = tool.get_history()
    assert res_hist.ok is True
    assert "Hello Nyx" in res_hist.output

    # Limpeza
    res_clear = tool.clear()
    assert res_clear.ok is True


def test_project_watch_tool_hardware():
    tool = ProjectWatchTool()
    res = tool.get_hardware_status()
    assert res.ok is True
    assert "RAM:" in res.output
    assert "CPU:" in res.output
    assert "Disco" in res.output
    assert "cpu_percent" in res.meta
    assert "ram_percent" in res.meta


def test_project_watch_reports_ollama_cpu_gpu_placement(monkeypatch):
    import json
    import urllib.request

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"models": [
                {"name": "cpu-model", "size": 1000, "size_vram": 0},
                {"name": "gpu-model", "size": 1000, "size_vram": 500},
            ]}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    status, meta = ProjectWatchTool._get_ollama_status()
    assert "cpu-model (CPU)" in status
    assert "gpu-model (GPU parcial)" in status
    assert meta["models"][0]["placement"] == "CPU"


def test_project_watch_tool_git():
    tool = ProjectWatchTool()
    # Pasta atual não é .git após extração zip, deve retornar erro amigável sem quebrar
    res = tool.get_git_status({"path": "."})
    assert res.ok is False or "Git status" in res.output


def test_ui_tool_basic():
    tool = UITool(screenshots_dir=Path("assets/screenshots"))

    # Ações destrutivas identificadas corretamente
    assert tool.is_destructive("close_window", {}) is True
    assert tool.is_destructive("press_key", {"key": "alt+f4"}) is True
    assert tool.is_destructive("click_coordinate", {"x": 10, "y": 10}) is False

    # Listagem de janelas
    res_win = tool.list_windows()
    assert res_win.ok is True
    assert isinstance(res_win.output, str)

    # Path guard is unit-tested here; real capture uses an owned Windows fixture.
    res_scr = tool.take_screenshot({"filename": "../outside.png"})
    assert not res_scr.ok


def test_sprite_renderer_all_emotions():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841

    renderer = SpriteRenderer(scale=2)
    emotions = ["idle", "talk", "think", "surprised", "listening", "error", "sleep"]
    modes = ["assistida", "autonoma"]

    for emo in emotions:
        for mode in modes:
            pix = renderer.get_pixmap(emotion=emo, mode=mode, frame=0)
            assert pix is not None
            assert not pix.isNull()
            assert pix.width() == 36 * 2
            assert pix.height() == 36 * 2


def test_stt_wake_word_detection():
    stt = SpeechToText()

    match1, cmd1 = stt.process_wake_word("Ei Nyx, qual é a temperatura atual?")
    assert match1 is True
    assert cmd1 == "qual é a temperatura atual?"

    match2, cmd2 = stt.process_wake_word("Nyx crie um arquivo de notas")
    assert match2 is True
    assert cmd2 == "crie um arquivo de notas"

    match3, cmd3 = stt.process_wake_word("Como está o tempo?")
    assert match3 is False
    assert cmd3 == "Como está o tempo?"


def test_full_registry_integration():
    cfg = NyxConfig()
    registry = build_registry(cfg)

    # Verifica todas as 9 ferramentas registradas
    expected_tools = {
        "shell", "read_file", "write_file", "find_files", "delete_file",
        "macro_run", "ui_action", "clipboard", "project_status", "skills"
    }
    assert expected_tools.issubset(set(registry.names()))

    # Executa ferramenta project_status pelo registry
    res = registry.execute("project_status", {"action": "hardware"})
    assert res.ok is True
    assert "RAM:" in res.output
