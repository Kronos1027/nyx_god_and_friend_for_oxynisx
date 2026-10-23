"""Unit routing tests with explicit network/input fixtures; real UI lives in test_windows_live."""

import io
import json
import sys
from types import SimpleNamespace

import pytest

from tools.web_tool import WebTool
from tools.ui_tool import UITool


@pytest.fixture(autouse=True)
def network_fixture(monkeypatch):
    """Known payloads test parsing/routing, not current external availability."""
    def response(request, **kwargs):
        url = request.full_url
        if "duckduckgo" in url:
            return io.BytesIO(b"<html></html>")
        if "wikipedia" in url:
            data = ["Python", ["Python"], ["Fixture language"], ["https://example.test/python"]]
        elif "ipapi" in url:
            data = {"city": "Fixture City", "country": "Fixture Country", "latitude": 1, "longitude": 2}
        elif "wttr.in" in url:
            data = {"current_condition": [{"temp_C": "21"}], "nearest_area": [{"areaName": [{"value": "Fixture City"}]}]}
        else:
            raise AssertionError("Unexpected endpoint: " + url)
        return io.BytesIO(json.dumps(data).encode())
    monkeypatch.setattr("urllib.request.urlopen", response)


def test_web_tool_initialization():
    tool = WebTool()
    assert tool.timeout == 12
    assert "NyxAgent" in tool.user_agent


def test_web_tool_search_fallback():
    tool = WebTool()
    # Busca por termo conhecido
    res = tool.search({"query": "Python programming language"})
    assert res.ok is True
    assert "python" in res.output.lower() or "resultados da pesquisa" in res.output.lower()


def test_web_tool_dispatch():
    tool = WebTool()
    # Teste de validação de ação
    res = tool.run({"action": "invalid_action"})
    assert res.ok is False
    assert "desconhecida" in res.error.lower()


def test_network_failure_never_invents_a_city(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("offline fixture")
    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    result = WebTool().get_location()
    assert not result.ok and not result.meta.get("city")


def test_ui_tool_new_methods(monkeypatch):
    ui = UITool()
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    assert not ui.mouse_move({}).ok
    assert ui.run({"action": "open_url", "url": "https://example.com"}).ok
    assert ui.run({"action": "open_app", "app": "spotify"}).ok
    assert opened == ["https://example.com", "https://open.spotify.com"]
    assert not ui.run({"action": "close_app"}).ok
    assert not ui.run({"action": "click_element", "id": 9999}).ok
    assert not ui.run({"action": "kill_process"}).ok


def test_web_tool_weather_and_location():
    tool = WebTool()

    # 1. Localização
    res_loc = tool.get_location()
    assert res_loc.ok is True
    assert "localização" in res_loc.output.lower()

    # 2. Clima com query do usuário sanitizada
    res_w = tool.search({"query": "previsão do tempo hoje [localização]"})
    assert res_w.ok is True
    assert "tempo" in res_w.output.lower() or "previsão" in res_w.output.lower()


def test_ui_phase2_extended_features(monkeypatch):
    keys = []
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(press=lambda key: keys.append(key)))

    class MemoryClipboard:
        text = ""

        @classmethod
        def copy(cls, text):
            cls.text = text

        @classmethod
        def paste(cls):
            return cls.text

    monkeypatch.setitem(sys.modules, "pyperclip", MemoryClipboard)
    ui = UITool()

    # 1. DPI scale
    dpi = ui.get_dpi_scale()
    assert isinstance(dpi, float)
    assert dpi >= 1.0

    # 2. Clipboard set e get
    test_text = "Nyx AGI Phase 2 Test Text"
    res_set = ui.run({"action": "set_clipboard", "text": test_text})
    assert res_set.ok is True
    res_get = ui.run({"action": "get_clipboard"})
    assert res_get.ok is True
    assert test_text in res_get.output

    # 3. Volume
    res_vol = ui.run({"action": "set_volume", "volume_action": "up", "steps": 1})
    assert res_vol.ok is True
    res_mute = ui.run({"action": "mute_volume"})
    assert res_mute.ok is True

    # 4. Drag validação
    res_drag_fail = ui.run({"action": "mouse_drag"})
    assert res_drag_fail.ok is False
    assert "obrigatórios" in res_drag_fail.error

    # 5. Window resize/move validação
    res_res = ui.run({"action": "resize_window"})
    assert res_res.ok is False
    res_mov = ui.run({"action": "move_window"})
    assert res_mov.ok is False

