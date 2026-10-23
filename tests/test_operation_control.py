import pytest

from core.operation_control import OperationCancelled, OperationControl
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def test_emergency_requires_explicit_resume_and_never_replays():
    registry = ToolRegistry()
    calls = []
    registry.register(ToolSpec("observe", "test"), lambda p: calls.append(p) or ToolResult(True, "ok"))
    registry.control.stop(emergency=True)
    registry.control.stop()  # ordinary cancellation cannot remove emergency
    assert registry.execute("observe", {}).meta["blocked"]
    with pytest.raises(OperationCancelled):
        registry.control.begin()
    registry.control.resume()
    assert calls == []
    assert registry.execute("observe", {"new": True}).ok
    assert calls == [{"new": True}]


def test_regular_cancel_allows_a_new_task():
    control = OperationControl()
    control.stop()
    with pytest.raises(OperationCancelled):
        control.check()
    control.begin()
    control.check()


def test_ui_dispatch_rejects_cancelled_calls(tmp_path, monkeypatch):
    from tools.ui_tool import UITool
    ui = UITool(tmp_path)
    monkeypatch.setattr(ui, "click_coordinate", lambda p: pytest.fail("must not click"))
    ui.control.stop(emergency=True)
    assert not ui.run({"action": "click", "x": 100, "y": 100}).ok


@pytest.mark.parametrize("response", ["not found", '{"x_percent":101,"y_percent":50}',
                                     '{"x_percent":50,"y_percent":50}'])
def test_visual_uncertainty_bounds_or_late_cancel_never_clicks(tmp_path, monkeypatch, response):
    import sys
    from types import SimpleNamespace
    from tools.ui_tool import UITool
    ui = UITool(tmp_path)
    shot = tmp_path / "test.png"
    shot.write_bytes(b"test fixture, no real screenshot")
    monkeypatch.setattr(ui, "take_screenshot", lambda: ToolResult(True, meta={"path": str(shot), "width": 800, "height": 600}))
    monkeypatch.setattr(ui, "get_dpi_scale", lambda: 1)
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(click=lambda *a: pytest.fail("must not click")))
    def infer(*args, **kwargs):
        if response == '{"x_percent":50,"y_percent":50}':
            ui.control.stop(emergency=True)
        return {"response": response}
    monkeypatch.setattr("core.runtime_budget.post_ollama_json", infer)
    assert not ui.vision_locate_and_click({"target": "test target"}).ok
