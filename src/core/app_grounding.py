"""Ground simple application requests before unrelated navigation/commands."""
import re


_NAMED_APP = re.compile(
    r'^\s*(?:abra|abre|abrir|inicie|inicia|pode\s+abrir)\s+(?:(?:o|a)\s+)?'
    r'(?P<app>microsoft\s+edge|edge|google\s+chrome|chrome|windows\s+terminal|terminal|'
    r'discord|steam|obs(?:\s+studio)?|antigravity|spotify|whatsapp|zap)\s*[.!?]?\s*$', re.I)


def explicit_app_issue(goal, tool, params):
    match = _NAMED_APP.fullmatch(goal)
    navigation = (tool == 'browser' and params.get('action') in {'open','navigate','goto'}) or (
        tool == 'ui_action' and params.get('action') in {'open_url','url','browser'})
    if not match or not (navigation or tool == 'shell'):
        return None
    return (f'O pedido é abrir o aplicativo {match["app"]}. '
            'Use ui_action com action=open_app e o nome exato solicitado. '
            'Se não estiver instalado, informe o erro real; não substitua por outro navegador.')
