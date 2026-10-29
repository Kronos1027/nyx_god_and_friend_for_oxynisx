"""Resolve local installed executables without PATH/CWD guessing or shell commands."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import unicodedata


def normalized_name(value):
    return " ".join(unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().split()).removesuffix(".exe")


@dataclass(frozen=True)
class InstalledApp:
    name: str
    path: Path
    source: str


def executable_path(value):
    if not isinstance(value, str):
        return None
    value = os.path.expandvars(value.strip().strip('"'))
    if len(value) > 2048 or any(c in value for c in ('"', '\n', '\r', '\x00', '&', '|', '<', '>')):
        return None
    path = Path(value)
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')) or ':' in value[2:]:
        return None
    if path.suffix.casefold() != '.exe' or not path.is_file():
        return None
    return path.resolve()


def installed_apps():
    import winreg
    found = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\App Paths', 0, winreg.KEY_READ | view) as root:
                    for index in range(min(winreg.QueryInfoKey(root)[0], 2048)):
                        try:
                            name = winreg.EnumKey(root, index)
                            with winreg.OpenKey(root, name) as key:
                                path = executable_path(winreg.QueryValueEx(key, '')[0])
                            if path:
                                found.append(InstalledApp(Path(name).stem, path, 'Windows App Paths'))
                        except OSError:
                            continue
            except OSError:
                continue
    # Steam does not always register App Paths; use its installed client record.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            path = executable_path(winreg.QueryValueEx(key, 'SteamExe')[0])
            if path and path.name.casefold() == 'steam.exe':
                found.append(InstalledApp('Steam', path, 'Valve/Steam'))
    except OSError:
        pass
    system = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32'
    for name, binary in (('Bloco de notas', 'notepad.exe'), ('Calculadora', 'calc.exe'), ('Paint', 'mspaint.exe')):
        path = executable_path(str(system / binary))
        if path:
            found.append(InstalledApp(name, path, 'Windows System32'))
    return list({(app.name.casefold(), str(app.path).casefold()): app for app in found}.values())


def resolve_app(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 2048:
        raise ValueError('Informe o nome do aplicativo instalado.')
    query = query.strip()
    catalog = installed_apps()
    path = executable_path(query)
    if path:
        registered = [app for app in catalog if app.path == path]
        roots = [Path(value).resolve() for value in (os.environ.get('WINDIR'), os.environ.get('ProgramFiles'),
                 os.environ.get('ProgramFiles(x86)')) if value]
        if registered:
            return registered[0]
        if any(root in path.parents for root in roots):
            return InstalledApp(path.stem, path, 'Pasta de aplicativos do Windows')
        raise ValueError('Executável não registrado como aplicativo instalado.')
    if not re.fullmatch(r'[\w .-]{1,80}', query) or Path(query).suffix.casefold() not in ('', '.exe'):
        raise ValueError('Use somente o nome de um aplicativo; comandos, argumentos e scripts não são aceitos.')
    key = normalized_name(query)
    matches = [app for app in catalog if key in (normalized_name(app.name), normalized_name(app.path.stem))]
    unique = {str(app.path).casefold(): app for app in matches}
    if len(unique) != 1:
        raise ValueError('Aplicativo não encontrado ou nome ambíguo. Consulte list_installed_apps com query antes de tentar novamente.')
    return next(iter(unique.values()))


def matching_windows(executable):
    import psutil
    import pygetwindow as gw
    import win32process
    result = []
    for window in gw.getAllWindows():
        if not window.visible or not window.title:
            continue
        try:
            _, pid = win32process.GetWindowThreadProcessId(window._hWnd)
            process = psutil.Process(pid)
            if Path(process.exe()).resolve() == executable:
                result.append({'title': window.title, 'hwnd': window._hWnd, 'pid': pid,
                               'created': process.create_time()})
        except (OSError, psutil.Error):
            continue
    return result
