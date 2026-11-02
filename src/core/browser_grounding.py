"""Ground browser conclusions in content and effects observed during this task."""
import re


_BROWSER_GOAL = re.compile(r'https?://|\b(?:navegador|abas?)\b', re.I)
_CODE_REQUEST = re.compile(
    r'\b(?:informe|diga|mostre|leia|confira|qual)\b[^.!?\n]{0,160}\bc[oó]digo\b', re.I)
_CODE_VALUE = re.compile(
    r'\bc[oó]digo\b(?P<label>[^\d\r\n:;.!?]{0,80}):?\s*(?P<value>\d{1,32})(?![\w-]|\.\d)', re.I)
_NAVIGATION = {'open', 'navigate', 'new_tab', 'switch_tab', 'close_tab', 'close'}
_CONTENT_MUTATIONS = _NAVIGATION | {'click', 'type', 'select', 'press', 'back', 'forward', 'reload'}
_FAILURE = re.compile(
    r'\bnão\s+(?:consegui|foi possível|pude|tenho certeza|confirmei|verifiquei)\b|'
    r'\b(?:falhou|falha|erro|sem confirmação)\b', re.I)
_COMPLETION = re.compile(
    r'\b(?:baixei|salvei|reproduzi|pausei|concluí)\b|'
    r'\b(?:download|arquivo|mídia)\b[^.!?\n]{0,60}\b(?:concluíd[oa]|salv[oa]|tocando|pausad[oa])\b', re.I)
_CODE_ASSERTION = re.compile(r'\bc[oó]digo\b[^.!?\n]{0,100}(?::|\bé\b)\s*[^\s.!?]', re.I)


def _observed_codes(text):
    """Only use explicit numeric code labels in body text, never titles or URLs."""
    values = set()
    for match in _CODE_VALUE.finditer(text):
        # A negated example ("código não é 123") is not an observed value.
        if not re.search(r'\b(?:não|nao|sem)\b', match['label'], re.I):
            values.add(match['value'])
    return values


def _honest_failure(speech, steps):
    """A real failed attempt may end honestly, without inventing an outcome."""
    return (bool(_FAILURE.search(speech)) and not _observed_codes(speech)
            and not _CODE_ASSERTION.search(speech)
            and not _COMPLETION.search(speech)
            and any(not step.get('ok') or not step.get('verified') for step in steps))


def _code_issue(steps, speech):
    # A read from before a successful mutation cannot establish the current page.
    boundary = max((index for index, step in enumerate(steps)
                    if step.get('ok') and step.get('params', {}).get('action') in _CONTENT_MUTATIONS),
                   default=-1)
    reads = [step for step in steps[boundary + 1:]
             if step.get('ok') and step.get('verified') and step.get('params', {}).get('action') == 'read']
    if not reads:
        return ('O pedido exige o código do conteúdo da página atual. Ainda não há leitura verificada '
                'depois da última navegação ou alteração. Use read; título, URL e lista de abas não '
                'comprovam esse código. Se a leitura falhou, informe o último erro real sem adivinhar.')
    # Only the latest body observation is current; older values may have changed.
    expected = _observed_codes(str(reads[-1].get('output') or ''))
    if not expected:
        # Truncation or a non-numeric code cannot be resolved by this narrow check.
        return None
    answer = re.sub(r'https?://\S+', '', speech, flags=re.I)
    claims = _observed_codes(answer)
    present = {value for value in expected if re.search(r'(?<!\w)' + re.escape(value) + r'(?!\w)', answer)}
    if (claims - expected) or not present:
        return ('A resposta não corresponde ao código numérico explicitamente observado no conteúdo. '
                'Copie o valor da última leitura verificada, sem usar o nome da aba, título ou URL. '
                'Se houver vários códigos, identifique o rótulo pedido; não invente outro valor.')
    return None


def browser_sequence_issue(goal, steps, tool, speech=''):
    """Return replanning feedback for an unsupported browser completion.

    This is a narrow consistency check, not a factual verifier for arbitrary web
    prose. Backend refs, permissions and independent acceptance remain necessary.
    """
    browser_steps = [step for step in steps if step.get('tool') == 'browser']
    if tool != 'none' or not _BROWSER_GOAL.search(goal):
        return None
    if _honest_failure(speech, browser_steps):
        return None
    from core.browser_context import browser_planning_state
    from core.browser_fields import pending_fields
    state = browser_planning_state(browser_steps)
    pending = pending_fields(state)
    if pending:
        return ('O pedido ainda tem campos explícitos sem digitação verificada: '
                + ', '.join(item['name'] for item in pending)
                + '. Preencha os valores exatos pedidos antes de clicar ou declarar conclusão.')
    if re.search(r'\bpreench\w*\b',goal,re.I) and re.search(r'\bcom\b',goal,re.I):
        if not any(step.get('verified') and step.get('params',{}).get('action')=='type' for step in browser_steps):
            return 'Nenhum preenchimento foi verificado. Inspecione os campos e digite os valores pedidos; não declare o cadastro concluído.'
        if re.search(r'\b(?:salve|envie|enviar|salvar)\b',goal,re.I):
            clicks=[index for index,step in enumerate(browser_steps) if step.get('ok') and step.get('params',{}).get('action')=='click']
            if not clicks or not any(step.get('ok') and step.get('verified') and step.get('params',{}).get('action') in {'read','wait_text'}
                                     for step in browser_steps[clicks[-1]+1:]):
                return 'Depois de preencher e clicar, leia a confirmação atual da página antes de afirmar que o cadastro foi enviado ou salvo.'
    if _CODE_REQUEST.search(goal):
        issue = _code_issue(browser_steps, speech)
        if issue:
            return issue
    if re.search(r'\b(?:baixe|baixar|download|descarregue)\b', goal, re.I):
        if not any(step.get('ok') and step.get('verified')
                   and step.get('params', {}).get('action') == 'download' for step in browser_steps):
            return ('O pedido exige baixar um arquivo. Ainda não existe download verificado nesta tarefa. '
                    'Use download com a URL observada e o caminho solicitado; abrir o link ou ler a '
                    'página não comprova um arquivo salvo. Se falhou, informe o último erro real.')
    if not (re.search(r'\b(?:reproduz\w*|toque|play)\b', goal, re.I)
            and re.search(r'\bpaus\w*\b', goal, re.I)):
        return None
    states = [step.get('media_state') for step in browser_steps if step.get('ok') and step.get('verified')]
    if 'playing' in states and 'paused' in states[states.index('playing') + 1:]:
        return None
    return ('O pedido exige reproduzir e depois pausar. Ainda não há observação verificada dos dois estados nessa ordem. '
            'Use media_play e observe avanço de tempo, depois media_pause e confira pausa; informe a falha real se houver.')
