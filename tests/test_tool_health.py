from audit.logger import AuditLogger
from tools.registry import ToolRegistry
from ui.tool_health import ToolHealthDialog


def test_health_reset_preserves_manual_disables_and_emergency(qapp, tmp_path):
    registry = ToolRegistry()
    for _ in range(3):
        registry.breaker.record('ui_action', {'action': 'open_app', 'app': 'Discord'}, False)
    registry.disabled_tools.add('shell')
    registry.control.stop(emergency=True)
    audit = AuditLogger(tmp_path)
    dialog = ToolHealthDialog(registry, audit)
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 2).text() == 'Discord'
    dialog.reset_button.click()
    assert registry.disabled_tools == {'shell'}
    assert registry.control.is_cancelled()
    assert registry.breaker.snapshot() == []
    assert audit.read_all()[-1]['event'] == 'circuit_breaker_reset'
    dialog.close()
    from PyQt6 import sip
    sip.delete(dialog)
