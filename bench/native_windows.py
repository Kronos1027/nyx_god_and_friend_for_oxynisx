"""Independent Win32 observations. No imports from Nyx tooling or verifier."""
import os
import unicodedata


APPS = {
    'calculator': {'prompt':'Abre a calculadora.', 'aliases':('calculadora','calculator','calc'),
                   'processes':('calculatorapp.exe','calculator.exe','calc.exe'), 'hosted_titles':('calculadora','calculator')},
    'notepad': {'prompt':'Abre o Bloco de notas.', 'aliases':('bloco de notas','notepad','bloco de notas do windows'),
                'processes':('notepad.exe',), 'hosted_titles':('bloco de notas','notepad')},
    'paint': {'prompt':'Abre o Paint.', 'aliases':('paint','mspaint','microsoft paint'),
              'processes':('mspaint.exe','paintstudio.view.exe'), 'hosted_titles':('paint',)},
}


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text)) if not unicodedata.combining(c)).casefold().strip()


def matches(window, expectation):
    process = window['process'].casefold()
    if process in expectation['processes']:
        return True
    return (process == 'applicationframehost.exe'
            and any(title == fold(window['title']) for title in expectation.get('hosted_titles', ()))
            and any(name.casefold() in expectation['processes'] for name in window.get('child_processes', ())))


def visible_windows():
    """Titles/HWNDs are transient verification data and must not be published."""
    if os.name != 'nt':
        raise RuntimeError('A observação independente exige Windows.')
    import ctypes
    from ctypes import wintypes as w
    import psutil

    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.EnumChildWindows.argtypes = [w.HWND, callback_type, w.LPARAM]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.IsWindow.argtypes = [w.HWND]
    user.GetWindowTextLengthW.argtypes = [w.HWND]
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetForegroundWindow.restype = w.HWND
    dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
    dwm.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
    dwm.DwmGetWindowAttribute.restype = w.LONG
    foreground = user.GetForegroundWindow()
    rows = []
    failures = []
    def observe(hwnd, unused):
        if not user.IsWindowVisible(hwnd):
            return True
        cloaked = w.DWORD()
        if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
            if user.IsWindow(hwnd):
                failures.append('DWM visibility query failed')
            return True
        if cloaked.value:
            return True
        length = min(2048, user.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length+1)
        user.GetWindowTextW(hwnd, title, length+1)
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            process = psutil.Process(pid.value).name()
        except psutil.Error:
            process = ''
        child_processes = set()
        if process.casefold() == 'applicationframehost.exe':
            def observe_child(child, unused):
                child_pid = w.DWORD()
                user.GetWindowThreadProcessId(child, ctypes.byref(child_pid))
                try:
                    child_processes.add(psutil.Process(child_pid.value).name())
                except psutil.Error:
                    pass
                return True
            user.EnumChildWindows(hwnd, callback_type(observe_child), 0)
        rows.append({'hwnd':int(hwnd), 'pid':pid.value, 'title':title.value,
                     'process':process, 'child_processes':sorted(child_processes), 'foreground':hwnd==foreground})
        return True
    if not user.EnumWindows(callback_type(observe), 0):
        raise OSError('EnumWindows não concluiu a observação independente.')
    if failures:
        raise OSError('A observação independente não confirmou visibilidade DWM de todas as janelas.')
    return rows


def verify_app(key):
    windows = [window for window in visible_windows() if matches(window, APPS[key])]
    return {'ok':bool(windows), 'matching_visible_windows':len(windows),
            'foreground_match':any(window['foreground'] for window in windows),
            'process_signals':sorted({window['process'] for window in windows}),
            'check':'independent Win32 window, DWM uncloaked and process; UWP host requires app title and child process'}
