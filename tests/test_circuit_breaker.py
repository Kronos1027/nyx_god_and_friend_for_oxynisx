from core.circuit_breaker import CircuitBreaker
from tools.registry import ToolRegistry, ToolResult, ToolSpec


def test_failures_are_scoped_and_manual_disable_survives_reset():
    registry = ToolRegistry()
    registry.register(ToolSpec("ui_action", "UI"), lambda p: ToolResult(p["action"] != "open_app"))
    failing = {"action": "open_app", "app": "Discord"}
    for _ in range(3):
        assert not registry.execute("ui_action", failing).ok
    assert registry.execute("ui_action", failing).meta["circuit_breaker"]
    assert registry.execute("ui_action", {"action": "list_windows"}).ok
    assert registry.breaker.blocked("ui_action", {"action": "open_app", "app": "Calculadora"}) is None
    registry.disabled_tools.add("ui_action")
    registry.breaker.reset()
    assert not registry.execute("ui_action", {"action": "list_windows"}).ok


def test_unverified_never_opens_breaker():
    breaker = CircuitBreaker()
    params = {"action": "click_element", "hwnd": 123}
    for _ in range(8):
        breaker.record("ui_action", params, True)
        breaker.observe("ui_action", params, False)
    assert breaker.blocked("ui_action", params) is None
    assert breaker.states[breaker.key("ui_action", params)].unverified == 8


def test_cooldown_one_probe_backoff_and_recovery():
    now = [0]
    breaker = CircuitBreaker(clock=lambda: now[0], cooldown=60)
    params = {"action": "open_app", "app": "Discord"}
    for _ in range(3):
        breaker.record("ui_action", params, False)
    assert breaker.blocked("ui_action", params)["retry_after_s"] == 60
    now[0] = 60
    assert breaker.blocked("ui_action", params, reserve=True) is None
    assert breaker.blocked("ui_action", params, reserve=True)
    breaker.record("ui_action", params, False)
    assert breaker.blocked("ui_action", params)["retry_after_s"] == 120
    now[0] = 180
    assert breaker.blocked("ui_action", params, reserve=True) is None
    breaker.record("ui_action", params, True)
    assert breaker.blocked("ui_action", params) is None


def test_target_aliases_and_reset_scope():
    breaker = CircuitBreaker()
    assert breaker.key("ui_action", {"action": "open_app", "app": "Steam"}) == breaker.key(
        "ui_action", {"action": "open_app", "app_name": " steam "})
    for tool in ("browser", "ui_action"):
        for _ in range(3):
            breaker.record(tool, {}, False)
    breaker.reset("browser")
    assert breaker.blocked("browser", {}) is None
    assert breaker.blocked("ui_action", {})


def test_operation_alias_and_query_are_independent_scopes():
    breaker = CircuitBreaker()
    for _ in range(3):
        breaker.record('skills', {'op': 'run', 'name': 'example'}, False)
        breaker.record('web', {'action': 'search', 'query': 'first'}, False)
    assert breaker.blocked('skills', {'op': 'get', 'name': 'example'}) is None
    assert breaker.blocked('web', {'action': 'search', 'query': 'second'}) is None
