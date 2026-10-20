import sys

from tools.clipboard_io import copy_text


def test_copy_retries_temporary_windows_clipboard_lock(monkeypatch):
    import time

    class BusyClipboard:
        attempts = 0
        content = None

        @classmethod
        def copy(cls, text):
            cls.attempts += 1
            if cls.attempts < 3:
                raise RuntimeError("Error calling OpenClipboard ([WinError 0])")
            cls.content = text

    monkeypatch.setitem(sys.modules, "pyperclip", BusyClipboard)
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    copy_text("Nyx")
    assert BusyClipboard.attempts == 3
    assert BusyClipboard.content == "Nyx"
    assert sleeps == [0.04, 0.08]


def test_copy_does_not_retry_unrelated_errors(monkeypatch):
    class BrokenClipboard:
        @staticmethod
        def copy(text):
            raise RuntimeError("clipboard backend missing")

    monkeypatch.setitem(sys.modules, "pyperclip", BrokenClipboard)
    try:
        copy_text("Nyx")
    except RuntimeError as exc:
        assert "backend missing" in str(exc)
    else:
        raise AssertionError("expected clipboard failure")
