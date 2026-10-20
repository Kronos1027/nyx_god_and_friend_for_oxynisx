"""Testes da FASE 3: UI Generativa e WindowManager (O Grande Sábio)"""

from PyQt6.QtWidgets import QApplication
import pytest

from ui.tokens import THEMES, get_theme, generate_stylesheet
from ui.window_manager import WindowManager
from tools.ui_tool import UITool


@pytest.fixture(scope="session")
def qapp():
    """Garante que a QApplication exista para testes de widgets."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_theme_tokens():
    assert "nyx_neon" in THEMES
    assert "anime_cyber" in THEMES
    assert "minimal" in THEMES

    neon = get_theme("nyx_neon")
    assert neon.name == "Nyx Neon"
    assert "#00F0FF" in neon.fg_color

    # Fallback para tema desconhecido
    fb = get_theme("non_existent_theme")
    assert fb.name == "Nyx Neon"

    qss = generate_stylesheet(neon)
    assert "GenerativeWindowRoot" in qss
    assert neon.bg_color in qss


def test_window_manager_lifecycle(qapp):
    wm = WindowManager.get_instance()

    spec = {
        "title": "Monitor de Status",
        "theme": "nyx_neon",
        "width": 400,
        "height": 300,
        "components": [
            {"id": "c_text", "type": "text", "title": "Missão", "value": "Fase 3 em execução"},
            {"id": "c_prog", "type": "progress", "value": 50, "max": 100},
            {"id": "c_chart", "type": "chart", "data": {"GPU": 80, "CPU": 25}},
            {"id": "c_steps", "type": "steps", "steps": [{"name": "Passo 1", "status": "success"}]},
            {"id": "c_term", "type": "terminal_log", "value": "Iniciando...\nPronto."},
            {"id": "c_tele", "type": "telemetry"},
        ],
    }

    # 1. Spawn
    win_id = wm.spawn(spec)
    assert win_id is not None
    assert win_id in wm.windows

    # 2. List
    wins = wm.list_windows()
    assert any(w["id"] == win_id for w in wins)

    # 3. Update component
    ok_up = wm.update(win_id, {"component_id": "c_text", "value": "Missão Atualizada!"})
    assert ok_up is True

    # 4. Close
    ok_close = wm.close(win_id)
    assert ok_close is True
    assert win_id not in wm.windows

    # 5. Close non-existent
    assert wm.close("inexistent_win") is False


def test_ui_tool_generative_dispatch(qapp):
    ui = UITool()

    # 1. Spawn via UI tool
    spec = {
        "title": "Janela Teste UITool",
        "components": [
            {"id": "t1", "type": "text", "value": "Olá mundo"},
        ],
    }
    res_spawn = ui.run({"action": "spawn_window", "spec": spec})
    assert res_spawn.ok is True
    win_id = res_spawn.meta["window_id"]

    # 2. List via UI tool
    res_list = ui.run({"action": "list_generative_windows"})
    assert res_list.ok is True
    assert res_list.meta["count"] >= 1

    # 3. Update via UI tool
    res_update = ui.run({
        "action": "update_window",
        "window_id": win_id,
        "component_id": "t1",
        "value": "Texto alterado com sucesso",
    })
    assert res_update.ok is True

    # 4. Close via UI tool
    res_close = ui.run({"action": "close_generative_window", "window_id": win_id})
    assert res_close.ok is True

    # 5. Fechar novamente deve falhar graciosamente
    res_close_again = ui.run({"action": "close_generative_window", "window_id": win_id})
    assert res_close_again.ok is False
