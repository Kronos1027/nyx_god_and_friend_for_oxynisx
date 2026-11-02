import itertools
import sys
from types import SimpleNamespace

import pytest

from tools.windows_targets import focus


@pytest.mark.parametrize('native_succeeds', [True, False])
def test_focus_fallback_uses_native_window_api_and_preserves_denial(monkeypatch, native_succeeds):
    active, calls, links = [], [], []
    def activate():
        raise OSError('initial activation denied')
    window = SimpleNamespace(_hWnd=42, isMinimized=False, isActive=False, activate=activate)
    def native(hwnd):
        calls.append(hwnd)
        if not native_succeeds:
            raise OSError('native focus denied')
        active.append(window)
    monkeypatch.setitem(sys.modules, 'pygetwindow', SimpleNamespace(getActiveWindow=lambda:active[-1] if active else None))
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(IsWindowEnabled=lambda hwnd:True,
        GetForegroundWindow=lambda:99, SetForegroundWindow=native))
    monkeypatch.setitem(sys.modules, 'win32api', SimpleNamespace(GetCurrentThreadId=lambda:1, SetLastError=lambda value:None))
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(
        GetWindowThreadProcessId=lambda hwnd:(2 if hwnd==99 else 3, 100),
        AttachThreadInput=lambda *args:links.append(args)))
    monkeypatch.setitem(sys.modules, 'pywinauto', SimpleNamespace(
        Desktop=lambda **kwargs:pytest.fail('Focus must not depend on UIA control metadata')))
    clock = itertools.count(0, .1)
    monkeypatch.setattr('tools.windows_targets.time.monotonic', lambda:next(clock))
    monkeypatch.setattr('tools.windows_targets.time.sleep', lambda seconds:None)
    control = SimpleNamespace(check=lambda:None)
    if native_succeeds:
        focus(window, control)
    else:
        with pytest.raises(ValueError, match='native focus denied'):
            focus(window, control)
    assert calls == [42]
    assert links == [(1,2,True),(1,3,True),(1,3,False),(1,2,False)]


def test_failed_detach_cannot_leave_a_reusable_worker(monkeypatch):
    from tools.windows_targets import _synchronize_focus
    monkeypatch.setitem(sys.modules, 'win32gui', SimpleNamespace(GetForegroundWindow=lambda:99,
                                                               SetForegroundWindow=lambda hwnd:None))
    monkeypatch.setitem(sys.modules, 'win32api', SimpleNamespace(GetCurrentThreadId=lambda:1, SetLastError=lambda value:None))
    def attach(own, thread, enabled):
        if not enabled:
            raise OSError('detach unavailable')
    monkeypatch.setitem(sys.modules, 'win32process', SimpleNamespace(
        GetWindowThreadProcessId=lambda hwnd:(2,100), AttachThreadInput=attach))
    with pytest.raises(SystemExit, match='auxiliar encerrado'):
        _synchronize_focus(42, SimpleNamespace(check=lambda:None))
