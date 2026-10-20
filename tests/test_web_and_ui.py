"""Testes para o subsistema de Pesquisa Web e Automação Avançada do Windows 11 (estilo Manus/Kimi K3)"""

from tools.web_tool import WebTool
from tools.ui_tool import UITool


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


def test_ui_tool_new_methods():
    ui = UITool()

    # 1. Obter janela ativa
    res_win = ui.get_active_window()
    assert res_win.ok is True

    # 2. Scroll
    res_scroll = ui.mouse_scroll({"clicks": 1})
    assert res_scroll.ok is True
    assert "scroll" in res_scroll.output.lower()

    # 3. Validação de coordenadas
    res_err = ui.mouse_move({})
    assert res_err.ok is False
    assert "obrigatórias" in res_err.error.lower()

    # 4. Abertura de URL e inspeção UIA
    res_url = ui.run({"action": "open_url", "url": "https://example.com"})
    assert res_url.ok is True
    assert "navegador" in res_url.output.lower()

    # 5. Redirecionamento de serviço (ex: spotify)
    res_spotify = ui.run({"action": "open_app", "app": "spotify"})
    assert res_spotify.ok is True
    assert "spotify.com" in res_spotify.output.lower()

    # 6. Inspeção de elementos da janela ativa (robusto)
    res_elem = ui.run({"action": "inspect_elements"})
    assert res_elem.ok is True
    assert "janela ativa" in res_elem.output.lower()

    # 7. Listagem de aplicativos em execução
    res_apps = ui.run({"action": "list_apps"})
    assert res_apps.ok is True
    assert "aplicativo" in res_apps.output.lower()

    # 8. Validação de fechar app
    res_close = ui.run({"action": "close_app"})
    assert res_close.ok is False
    assert "obrigatório" in res_close.error.lower()

    # 9. Validação de clique em elemento UIA por ID
    res_click_el = ui.run({"action": "click_element", "id": 9999})
    assert res_click_el.ok is False
    assert "não encontrado" in res_click_el.error.lower()

    # 10. Validação de finalização de processo via psutil
    res_kill = ui.run({"action": "kill_process"})
    assert res_kill.ok is False
    assert "obrigatório" in res_kill.error.lower()


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

