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
    return process == 'applicationframehost.exe' and any(
        title == fold(window['title']) for title in expectation.get('hosted_titles', ()))


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
    user.IsWindowVisible.argtypes = [w.HWND]
    user.GetWindowTextLengthW.argtypes = [w.HWND]
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.GetForegroundWindow.restype = w.HWND
    foreground = user.GetForegroundWindow()
    rows = []
    def observe(hwnd, unused):
        if not user.IsWindowVisible(hwnd):
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
        rows.append({'hwnd':int(hwnd), 'pid':pid.value, 'title':title.value,
                     'process':process, 'foreground':hwnd==foreground})
        return True
    if not user.EnumWindows(callback_type(observe), 0):
        raise OSError('EnumWindows não concluiu a observação independente.')
    return rows


def verify_app(key):
    windows = [window for window in visible_windows() if matches(window, APPS[key])]
    return {'ok':bool(windows), 'matching_visible_windows':len(windows),
            'foreground_match':any(window['foreground'] for window in windows),
            'process_signals':sorted({window['process'] for window in windows}),
            'check':'independent Win32 visible window and process; UWP host also requires app title'}
