"""Small retry for transient Windows clipboard ownership contention."""

from __future__ import annotations

import time


def copy_text(text: str, attempts: int = 8) -> None:
    import pyperclip

    for attempt in range(attempts):
        try:
            pyperclip.copy(text)
            return
        except Exception as exc:
            transient = "openclipboard" in str(exc).casefold()
            if not transient or attempt + 1 >= attempts:
                raise
            time.sleep(0.04 * (attempt + 1))
