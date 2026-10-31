import pytest

from tools.registry import ToolSpec
from tools.ui_tool import UITool


@pytest.mark.parametrize('action', ['list_windows', 'list_installed_apps', 'list_steam_games',
                                  'active_window', 'inspect_elements', 'read_element', 'screenshot'])
def test_read_only_desktop_operations_do_not_require_per_action_confirmation(action):
    spec = ToolSpec('ui_action', 'UI', sensitive_probe=UITool.is_sensitive)
    assert not spec.is_sensitive_for({'action': action})


@pytest.mark.parametrize('action', ['open_app', 'press_key', 'click_element', 'type_element',
                                  'set_clipboard', 'get_clipboard', 'close_app', 'kill_process',
                                  'spawn_window', 'screen_vision', 'unknown'])
def test_effects_clipboard_and_unknown_operations_remain_sensitive(action):
    spec = ToolSpec('ui_action', 'UI', sensitive_probe=UITool.is_sensitive)
    assert spec.is_sensitive_for({'action': action})


def test_malformed_subaction_fails_closed():
    spec = ToolSpec('ui_action', 'UI', sensitive_probe=UITool.is_sensitive)
    assert spec.is_sensitive_for({'action': []})


def test_production_registry_uses_the_observation_policy(tmp_path):
    from cli import build_registry
    from config import NyxConfig
    registry = build_registry(NyxConfig(allowed_roots=[tmp_path], log_dir=tmp_path / 'logs'))
    try:
        spec = registry.spec('ui_action')
        assert not spec.is_sensitive_for({'action': 'list_windows'})
        assert spec.is_sensitive_for({'action': 'type_element'})
        assert spec.is_destructive_for({'action': 'close_app'})
        assert spec.is_destructive_for({'action': 'press_key', 'key': 'alt+f4'})
    finally:
        registry.browser_session.close()
