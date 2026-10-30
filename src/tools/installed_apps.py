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
    # Per-machine installs can remain available when SteamExe is absent in HKCU.
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'Software\Valve\Steam', 0, winreg.KEY_READ | view) as key:
                directory = winreg.QueryValueEx(key, 'InstallPath')[0]
                path = executable_path(str(Path(directory) / 'steam.exe')) if isinstance(directory, str) else None
                if path:
                    found.append(InstalledApp('Steam', path, 'Valve/Steam'))
        except OSError:
            continue
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
    import pywintypes
    import win32process
    executable = Path(executable).resolve()
    result = []
    for window in gw.getAllWindows():
        if not window.visible or not window.title:
            continue
        try:
            _, pid = win32process.GetWindowThreadProcessId(window._hWnd)
            process = psutil.Process(pid)
            owner = _matching_owner(process, executable)
            # A closed/reused HWND or PID must not turn an unrelated window into proof.
            if owner and process.is_running() and win32process.GetWindowThreadProcessId(window._hWnd)[1] == pid:
                result.append({'title': window.title, 'hwnd': window._hWnd, 'pid': pid,
                               'created': process.create_time(), 'owner': owner})
        except (OSError, psutil.Error, pywintypes.error):
            continue
    return result


def _matching_owner(process, executable):
    """Match Steam's own renderer, never games or arbitrary child processes."""
    path = Path(process.exe()).resolve()
    if path == executable:
        return 'executable'
    if (executable.name.casefold() != 'steam.exe' or path.name.casefold() != 'steamwebhelper.exe'
            or executable.parent not in path.parents):
        return None
    created = process.create_time()
    ancestor = process
    seen = {process.pid}
    for _ in range(8):
        ancestor = ancestor.parent()
        if ancestor is None or ancestor.pid in seen:
            break
        seen.add(ancestor.pid)
        if ancestor.create_time() > created:
            return None
        if Path(ancestor.exe()).resolve() == executable and ancestor.is_running():
            return 'steam_renderer_with_client_ancestor'
    return None


def _read_keyvalues(path, *, maximum=65_536):
    """Parse only bounded Valve text KeyValues; no includes, directives or evaluation."""
    with path.open('rb') as source:
        raw = source.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Manifesto Steam excede o limite de leitura.')
    text = raw.decode('utf-8-sig')
    tokens = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
        elif text.startswith('//', index):
            end = text.find('\n', index)
            index = len(text) if end < 0 else end + 1
        elif text[index] in '{}':
            tokens.append((text[index], text[index]))
            index += 1
        elif text[index] == '"':
            index += 1
            value = []
            while index < len(text) and text[index] != '"':
                char = text[index]
                if char == '\\' and index + 1 < len(text) and text[index + 1] in ('\\', '"'):
                    index += 1
                    char = text[index]
                value.append(char)
                index += 1
            if index >= len(text):
                raise ValueError('String incompleta no manifesto Steam.')
            tokens.append(('text', ''.join(value)))
            index += 1
        else:
            raise ValueError('Formato de manifesto Steam não suportado.')
        if len(tokens) > 20_000:
            raise ValueError('Manifesto Steam contém itens em excesso.')
    position = 0

    def object_at(depth=0):
        nonlocal position
        if depth > 8:
            raise ValueError('Manifesto Steam excessivamente aninhado.')
        result = {}
        while position < len(tokens):
            kind, key = tokens[position]
            if kind == '}':
                if not depth:
                    raise ValueError('Fechamento inesperado no manifesto Steam.')
                position += 1
                return result
            position += 1
            if kind != 'text' or position >= len(tokens) or key.casefold() in result:
                raise ValueError('Chave inválida ou duplicada no manifesto Steam.')
            kind, value = tokens[position]
            position += 1
            if kind == '{':
                value = object_at(depth + 1)
            elif kind != 'text':
                raise ValueError('Valor inválido no manifesto Steam.')
            result[key.casefold()] = value
        if depth:
            raise ValueError('Objeto incompleto no manifesto Steam.')
        return result

    return object_at()


def _local_directory(value):
    if not isinstance(value, str) or '\x00' in value or any(c in value for c in '\r\n'):
        return None
    path = Path(value)
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')) or ':' in value[2:]:
        return None
    if not path.is_dir():
        return None
    resolved = path.resolve()
    return None if str(resolved).startswith(('\\\\', '//')) else resolved


def steam_game_catalog():
    """Read installed manifests from registered Steam libraries; never launch anything."""
    from itertools import islice
    steam = resolve_app('Steam').path.parent
    libraries = [steam]
    unreadable = 0
    for folder in ('steamapps', 'config'):
        source = steam / folder / 'libraryfolders.vdf'
        if not source.is_file():
            continue
        try:
            entries = _read_keyvalues(source, maximum=1_048_576).get('libraryfolders', {})
            if not isinstance(entries, dict):
                raise ValueError('Catálogo Steam inválido.')
            for key, entry in entries.items():
                if key.isdecimal():
                    path = _local_directory(entry.get('path') if isinstance(entry, dict) else entry)
                    if path is not None and path not in libraries:
                        libraries.append(path)
            break
        except (OSError, UnicodeError, ValueError):
            unreadable += 1
    games, examined, skipped = {}, 0, 0
    truncated = len(libraries) > 16
    for library in libraries[:16]:
        if examined >= 512:
            truncated = True
            break
        for manifest in islice((library / 'steamapps').glob('appmanifest_*.acf'), 513 - examined):
            if examined >= 512:
                truncated = True
                break
            examined += 1
            try:
                data = _read_keyvalues(manifest).get('appstate', {})
                if not isinstance(data, dict):
                    raise ValueError('Estado Steam inválido.')
                appid, name, directory = (data.get(key, '') for key in ('appid', 'name', 'installdir'))
                flags = data.get('stateflags', '')
                if (not all(isinstance(value, str) for value in (appid, name, directory, flags))
                        or not re.fullmatch(r'[0-9]{1,10}', appid) or manifest.stem != f'appmanifest_{appid}'
                        or not name.strip() or len(name) > 300 or any(ord(c) < 32 for c in name)
                        or not directory or directory in ('.', '..') or any(c in directory for c in '/\\:\x00')
                        or not flags.isdecimal() or len(flags) > 10):
                    raise ValueError('Campos Steam inválidos.')
                common = (library / 'steamapps' / 'common').resolve()
                installation = (common / directory).resolve()
                if common not in installation.parents or not installation.is_dir() or not int(flags) & 4:
                    skipped += 1
                    continue
                # These manifests are support runtimes, not games the user can choose.
                if name.startswith(('Steam Linux Runtime', 'Steamworks Common Redistributables', 'Proton ')):
                    continue
                games.setdefault(appid, {'appid': appid, 'name': name.strip(), 'needs_update': bool(int(flags) & 2)})
            except (OSError, UnicodeError, ValueError):
                unreadable += 1
    return {'games': sorted(games.values(), key=lambda item: normalized_name(item['name'])),
            'libraries_checked': min(len(libraries), 16), 'manifests_checked': examined,
            'unreadable': unreadable, 'incomplete': skipped, 'scan_truncated': truncated}
