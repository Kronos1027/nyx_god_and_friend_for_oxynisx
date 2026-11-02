"""Read-only installed-app denominator, independent of Nyx's app catalogue."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess

from bench.native_windows import APPS, fold, matches, visible_windows
from bench.catalog import NATIVE_CASES


def installed_inventory():
    names, complete, errors = set(), False, []
    if os.name != 'nt':
        return {'complete':False, 'apps':{}, 'errors':['Inventário requer Windows.']}
    executable = Path(os.environ.get('WINDIR', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = '[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); @(Get-StartApps | Select-Object -ExpandProperty Name) | ConvertTo-Json -Compress'
    try:
        result = subprocess.run([str(executable),'-NoProfile','-NonInteractive','-Command',script],
            capture_output=True,check=True,timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if len(result.stdout)>1_048_576:
            raise ValueError('Inventário excede o limite de leitura.')
        values = json.loads(result.stdout.decode('utf-8-sig'))
        if isinstance(values,str):
            values = [values]
        if not isinstance(values,list) or not all(isinstance(value,str) for value in values):
            raise ValueError('Formato do inventário de apps inválido.')
        names.update(fold(value) for value in values)
        complete = True
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        errors.append(type(exc).__name__+': inventário do Menu Iniciar indisponível.')
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\App Paths',0,winreg.KEY_READ|view) as key:
                    for index in range(min(winreg.QueryInfoKey(key)[0],2048)):
                        binary = winreg.EnumKey(key,index)
                        with winreg.OpenKey(key,binary) as entry:
                            path = os.path.expandvars(str(winreg.QueryValueEx(entry,'')[0]).strip('"'))
                        if not path.startswith(('\\\\','//')) and Path(path).is_absolute() and Path(path).is_file():
                            names.add(fold(Path(binary).stem))
            except OSError:
                continue
    try:
        windows = visible_windows()
    except OSError:
        windows = []
    system = Path(os.environ.get('WINDIR',r'C:\Windows'))
    fixed = {'calculator':system/'System32/calc.exe', 'notepad':system/'System32/notepad.exe',
             'paint':system/'System32/mspaint.exe', 'taskmanager':system/'System32/taskmgr.exe',
             'explorer':system/'explorer.exe'}
    apps = {}
    for key, expectation in APPS.items():
        aliases = {*expectation['aliases'],*(Path(p).stem for p in expectation['processes'])}
        methods = []
        if any(fold(alias) in names for alias in aliases):
            methods.append('registered_app')
        if key in fixed and fixed[key].is_file():
            methods.append('windows_binary')
        if any(matches(window,expectation) for window in windows):
            methods.append('visible_app_identity')
        apps[key] = {'installed':True if methods else False if complete else None,'methods':methods}
    return {'complete':complete,'apps':apps,'errors':errors,
            'scope':'Menu Iniciar/App Paths/binários Windows/janelas identificadas; sem varredura recursiva de disco.'}


def installed_cases(catalog, inventory):
    selected, excluded = [], []
    for case in catalog:
        if case.category != 'apps':
            selected.append(case)
            continue
        candidates = ('antigravity','vscode') if case.id=='apps-11' else (NATIVE_CASES[case.id],)
        found = next((key for key in candidates if inventory['apps'].get(key,{}).get('installed') is True),None)
        if found:
            selected.append(replace(case,target=found,route='native_app_ui'))
        else:
            known_absent = all(inventory['apps'].get(key,{}).get('installed') is False for key in candidates)
            excluded.append({'id':case.id,'targets':list(candidates),
                             'reason':'NOT_INSTALLED' if known_absent else 'INVENTORY_UNKNOWN'})
    return selected, excluded


def precheck_running(keys):
    """Never close a pre-existing app or infer ownership from its title."""
    import psutil
    windows = visible_windows()
    names = set()
    for process in psutil.process_iter(['name']):
        try:
            names.add((process.info['name'] or '').casefold())
        except psutil.Error:
            continue
    blocked = []
    for key in keys:
        expectation = APPS[key]
        visible = any(matches(window,expectation) for window in windows)
        # Explorer's desktop shell is shared and always running; only actual
        # Cabinet/Explore windows count as an already-open file explorer.
        running = key!='explorer' and any(name in names for name in expectation['processes'])
        if visible or running:
            blocked.append({'app':key,'error_code':'PRECHECK_CLOSE_APP',
                'message':f'Feche {expectation["aliases"][0]} antes de rodar este caso.',
                'ownership':'pre-existing or unproven; no process was closed'})
    return blocked
