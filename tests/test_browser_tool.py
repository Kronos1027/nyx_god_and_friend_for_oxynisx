"""Browser tool: URL safety, action dispatch and confirmation rules."""

from pathlib import Path

import pytest

from tools.browser_tool import (
    ALLOWED_SCHEMES,
    BrowserError,
    is_sensitive_action,
    make_browser_tool_func,
    validate_url,
)
from tools.registry import ToolSpec


class FakeSession:
    started = True

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.closed = False

    def open(self, url: str) -> dict:
        self.calls.append(("open", url))
        return {"url": url, "title": "Example", "ready": "complete"}

    def read_text(self) -> dict:
        return {"text": "Olá mundo", "url": "https://example.com", "title": "Example",
                "truncated": False, "chars": 10}

    def click(self, selector: str) -> str:
        self.calls.append(("click", selector))
        return "clicked"

    def type_text(self, selector: str, text: str) -> str:
        self.calls.append(("type", selector, text))
        return "typed"

    def wait_for(self, selector: str, timeout: float) -> bool:
        self.calls.append(("wait", selector, timeout))
        return True

    def screenshot(self, path: Path) -> Path:
        self.calls.append(("screenshot", str(path)))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"png")
        return Path(path)

    def extract_links(self, selector: str | None = None, limit: int = 50) -> list[dict]:
        self.calls.append(("extract_links", selector, limit))
        return [{"text": "Home", "href": "https://example.com/"}]

    def extract_tables(self, limit: int = 10) -> list[dict]:
        self.calls.append(("extract_tables", limit))
        return [{"headers": ["A", "B"], "rows": [["1", "2"]]}]

    def wait_for_text(self, text: str, timeout: float = 10.0) -> bool:
        self.calls.append(("wait_for_text", text, timeout))
        return True

    def scroll(self, direction: str = "down", amount: int = 500, selector: str | None = None) -> dict:
        self.calls.append(("scroll", direction, amount, selector))
        return {"found": True, "scrollY": amount, "scrollHeight": 2000, "clientHeight": 900, "atBottom": False}

    def list_tabs(self) -> list[dict]:
        self.calls.append(("list_tabs",))
        return [{"id": "tab-1", "title": "Example", "url": "https://example.com", "active": True}]

    def new_tab(self, url: str = "about:blank") -> dict:
        self.calls.append(("new_tab", url))
        return {"id": "tab-2", "title": "New Tab", "url": url}

    def switch_tab(self, tab_id: str) -> dict:
        self.calls.append(("switch_tab", tab_id))
        return {"id": tab_id, "title": "Switched", "url": "https://example.com/2"}

    def close_tab(self, tab_id: str | None = None) -> dict:
        self.calls.append(("close_tab", tab_id))
        return {"status": "closed", "remaining_tabs": 1}

    def status(self) -> dict:
        return {"title": "Example", "url": "https://example.com", "ready": "complete"}

    def close(self) -> None:
        self.closed = True


def tool(session: FakeSession, roots: list[Path] | None = None):
    return make_browser_tool_func(session, roots or [])


def test_validate_url_accepts_only_http_and_https():
    assert validate_url("https://example.com/a?b=1") == "https://example.com/a?b=1"
    assert validate_url("  http://localhost:8000  ") == "http://localhost:8000"
    assert ALLOWED_SCHEMES == ("http://", "https://")
    for bad in ("file:///C:/Windows/win.ini", "javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://x", "", "   ", "https://"):
        with pytest.raises(BrowserError):
            validate_url(bad)


def test_open_dispatches_and_reports_the_page():
    session = FakeSession()
    result = tool(session)({"action": "open", "url": "https://example.com"})

    assert result.ok is True
    assert session.calls == [("open", "https://example.com")]
    assert '"title": "Example"' in result.output


def test_read_returns_page_text():
    result = tool(FakeSession())({"action": "read"})
    assert result.ok is True
    assert result.output == "Olá mundo"
    assert result.meta["title"] == "Example"


def test_click_and_type_dispatch_with_selector():
    session = FakeSession()
    runner = tool(session)
    assert runner({"action": "click", "selector": "#go"}).ok is True
    assert runner({"action": "type", "selector": "#name", "text": "Nyx"}).ok is True
    assert session.calls == [("click", "#go"), ("type", "#name", "Nyx")]


def test_missing_selector_is_reported_not_raised():
    result = tool(FakeSession())({"action": "click"})
    assert result.ok is False
    assert "seletor" in result.error.lower()


def test_wait_uses_timeout_and_reports_ready():
    session = FakeSession()
    result = tool(session)({"action": "wait", "selector": ".row", "timeout": 3})
    assert result.ok is True
    assert session.calls == [("wait", ".row", 3.0)]


def test_screenshot_is_confined_to_allowed_roots(tmp_path):
    session = FakeSession()
    outside = tool(session)({"action": "screenshot", "path": str(tmp_path.parent / "escape.png")})
    assert outside.ok is False
    assert "pastas permitidas" in outside.error

    inside = tool(session, [tmp_path])({"action": "screenshot", "path": str(tmp_path / "shot.png")})
    assert inside.ok is True
    assert (tmp_path / "shot.png").read_bytes() == b"png"


def test_unknown_action_is_rejected():
    result = tool(FakeSession())({"action": "delete_everything"})
    assert result.ok is False
    assert "desconhecida" in result.error


def test_close_stops_the_browser():
    session = FakeSession()
    assert tool(session)({"action": "close"}).ok is True
    assert session.closed is True


def test_browser_errors_become_tool_errors():
    class Broken(FakeSession):
        def open(self, url: str) -> dict:
            raise BrowserError("navegador indisponível")

    result = tool(Broken())({"action": "open", "url": "https://example.com"})
    assert result.ok is False
    assert result.error == "navegador indisponível"


def test_click_and_type_are_the_sensitive_actions():
    assert is_sensitive_action("click") is True
    assert is_sensitive_action(" TYPE ") is True
    assert is_sensitive_action("read") is False
    assert is_sensitive_action("open") is False
    assert is_sensitive_action(None) is False

    spec = ToolSpec(
        name="browser",
        description="test",
        sensitive=False,
        sensitive_probe=lambda params: is_sensitive_action(params.get("action")),
    )
    assert spec.is_sensitive_for({"action": "click"}) is True
    assert spec.is_sensitive_for({"action": "read"}) is False


def test_extract_links_and_tables():
    session = FakeSession()
    runner = tool(session)
    links_res = runner({"action": "links", "limit": 10})
    assert links_res.ok is True
    assert '"Home"' in links_res.output
    assert session.calls[-1] == ("extract_links", None, 10)

    tables_res = runner({"action": "tables", "limit": 5})
    assert tables_res.ok is True
    assert '"headers"' in tables_res.output
    assert session.calls[-1] == ("extract_tables", 5)


def test_wait_text_and_scroll():
    session = FakeSession()
    runner = tool(session)
    wait_res = runner({"action": "wait_text", "text": "Bem-vindo", "timeout": 8})
    assert wait_res.ok is True
    assert session.calls[-1] == ("wait_for_text", "Bem-vindo", 8.0)

    scroll_res = runner({"action": "scroll", "direction": "down", "amount": 600})
    assert scroll_res.ok is True
    assert '"scrollY": 600' in scroll_res.output
    assert session.calls[-1] == ("scroll", "down", 600, None)


def test_tab_actions():
    session = FakeSession()
    runner = tool(session)
    tabs_res = runner({"action": "tabs"})
    assert tabs_res.ok is True
    assert "tab-1" in tabs_res.output

    new_tab_res = runner({"action": "new_tab", "url": "https://example.com/page"})
    assert new_tab_res.ok is True
    assert "tab-2" in new_tab_res.output

    switch_res = runner({"action": "switch_tab", "tab_id": "tab-1"})
    assert switch_res.ok is True

    close_res = runner({"action": "close_tab", "tab_id": "tab-2"})
    assert close_res.ok is True
