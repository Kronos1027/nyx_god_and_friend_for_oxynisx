"""Ground simple application requests before unrelated navigation/commands."""
import re
import unicodedata


_NAMED_APP = re.compile(
    r'^\s*(?:abra|abre|abrir|inicie|inicia|pode\s+abrir)\s+(?:(?:o|a)\s+)?'
    r'(?P<app>microsoft\s+edge|edge|google\s+chrome|chrome|windows\s+terminal|terminal|'
    r'discord|steam|obs(?:\s+studio)?|antigravity|spotify|whatsapp|zap|calculadora|calculator|'
    r'bloco\s+de\s+notas|notepad|paint|explorador(?:\s+de\s+arquivos)?|'
    r'configurações(?:\s+do\s+windows)?|gerenciador\s+de\s+tarefas)\s*[.!?]?\s*$', re.I)

_ALIASES = {
    'calculator': ('calculadora','calculator','calc','calc.exe'),
    'notepad': ('bloco de notas','notepad','notepad.exe'),
    'paint': ('paint','mspaint','mspaint.exe'),
    'explorer': ('explorador','explorador de arquivos','explorer','explorer.exe'),
    'settings': ('configuracoes','configuracoes do windows','settings','ms-settings:'),
    'taskmanager': ('gerenciador de tarefas','task manager','taskmgr','taskmgr.exe'),
    'edge': ('microsoft edge','edge','msedge','msedge.exe'),
    'chrome': ('google chrome','chrome','chrome.exe'),
    'terminal': ('windows terminal','terminal','wt','wt.exe'),
    'obs': ('obs','obs studio','obs64','obs64.exe'),
    'whatsapp': ('whatsapp','zap'),
}


def _canonical(value):
    value = ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(value))
                            if not unicodedata.combining(c)).casefold().split())
    return next((key for key, aliases in _ALIASES.items() if value in aliases), value)


def explicit_app_target(goal):
    match = _NAMED_APP.fullmatch(goal)
    return match['app'] if match else None


def explicit_app_issue(goal, tool, params, steps=()):
    app = explicit_app_target(goal)
    if not app:
        return None
    if tool == 'none' and any(step['tool']=='ui_action' and step.get('verified')
            and step['params'].get('action')=='open_app'
            and _canonical(step['params'].get('app') or step['params'].get('app_name') or step['params'].get('name')) == _canonical(app)
            for step in steps):
        return None
    if tool == 'ui_action':
        if params.get('action') in {'list_windows','list_installed_apps','get_active_window'}:
            return None
        if params.get('action') == 'open_app' and _canonical(
                params.get('app') or params.get('app_name') or params.get('name')) == _canonical(app):
            return None
    return (f'O pedido é abrir o aplicativo {app}. '
            'Use ui_action com action=open_app e o nome exato solicitado. '
            'A ferramenta calculator faz contas e não abre a Calculadora. '
            'Só conclua após observar a janela solicitada. Se não estiver instalado, informe o erro real; '
            'não substitua por outro aplicativo ou navegador.')
