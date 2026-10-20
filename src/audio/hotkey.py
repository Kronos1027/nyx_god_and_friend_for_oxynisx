"""Nyx — audio/hotkey.py (Fase 3: Hotkeys Globais do Windows)

Atalhos globais nativos para Windows 11 via ctypes e user32.dll:
- Ctrl+Space: Ativa escuta / foca o agente Nyx (modo assistido)
- Ctrl+Shift+Space: Alterna modo autônomo com fonte legítima 'ui_hotkey'
- Totalmente em background sem bloquear a interface gráfica
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import sys
import threading
from typing import Callable

log = logging.getLogger(__name__)

# Modificadores Win32
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_SPACE = 0x20
WM_HOTKEY = 0x0312

HOTKEY_LISTEN_ID = 101
HOTKEY_AUTONOMOUS_ID = 102
HOTKEY_KILL_SWITCH_ID = 103
VK_K = 0x4B


class HotkeyListener:
    """Escuta atalhos globais do sistema operacional em uma thread dedicada."""

    def __init__(
        self,
        on_listen: Callable[[], None] | None = None,
        on_toggle_autonomous: Callable[[], None] | None = None,
        on_kill_switch: Callable[[], None] | None = None,
    ) -> None:
        self.on_listen = on_listen
        self.on_toggle_autonomous = on_toggle_autonomous
        self.on_kill_switch = on_kill_switch
        self._thread: threading.Thread | None = None
        self._running = False
        self._thread_id: int | None = None

    def start(self) -> None:
        """Inicia o listener em background se estiver em ambiente Windows."""
        if sys.platform != "win32":
            log.info("HotkeyListener: ambiente não-Windows. Ignorando registro de hotkeys.")
            return

        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._msg_loop, daemon=True, name="NyxHotkeyThread")
        self._thread.start()

    def stop(self) -> None:
        """Encerra a thread de captura de atalhos."""
        self._running = False
        if sys.platform == "win32" and self._thread_id:
            user32 = ctypes.windll.user32
            # Posta WM_QUIT para desempacar a fila de mensagens
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _msg_loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        # 1. Registra Ctrl+Space (Escuta)
        r1 = user32.RegisterHotKey(
            None,
            HOTKEY_LISTEN_ID,
            MOD_CONTROL | MOD_NOREPEAT,
            VK_SPACE,
        )

        # 2. Registra Ctrl+Shift+Space (Toggle Autônomo)
        r2 = user32.RegisterHotKey(
            None,
            HOTKEY_AUTONOMOUS_ID,
            MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
            VK_SPACE,
        )

        # 3. Registra Ctrl+Alt+K (Kill-Switch de Emergência)
        r3 = user32.RegisterHotKey(
            None,
            HOTKEY_KILL_SWITCH_ID,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
            VK_K,
        )

        if not r1:
            log.warning("Não foi possível registrar o atalho global Ctrl+Space (já em uso).")
        if not r2:
            log.warning("Não foi possível registrar o atalho global Ctrl+Shift+Space.")
        if not r3:
            log.warning("Não foi possível registrar o atalho global de Kill-Switch Ctrl+Alt+K.")

        log.info("HotkeyListener ativo: Ctrl+Space (Escuta), Ctrl+Shift+Space (Autônomo), Ctrl+Alt+K (Kill-Switch)")

        msg = ctypes.wintypes.MSG()
        try:
            while self._running:
                # Espera mensagens da fila da thread
                res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if res in (0, -1):
                    break

                if msg.message == WM_HOTKEY:
                    hotkey_id = msg.wParam
                    if hotkey_id == HOTKEY_LISTEN_ID and self.on_listen:
                        self.on_listen()
                    elif hotkey_id == HOTKEY_AUTONOMOUS_ID and self.on_toggle_autonomous:
                        self.on_toggle_autonomous()
                    elif hotkey_id == HOTKEY_KILL_SWITCH_ID and self.on_kill_switch:
                        self.on_kill_switch()

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnregisterHotKey(None, HOTKEY_LISTEN_ID)
            user32.UnregisterHotKey(None, HOTKEY_AUTONOMOUS_ID)
            user32.UnregisterHotKey(None, HOTKEY_KILL_SWITCH_ID)
            log.info("HotkeyListener finalizado.")
