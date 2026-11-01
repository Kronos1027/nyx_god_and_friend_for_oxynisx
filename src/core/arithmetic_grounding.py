"""Narrow grounding checks for explicit read-files-and-sum requests."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import ntpath
import re


def file_sum_goal(goal):
    return (re.search(r'\b(?:leia|ler|read)\b', goal, re.I)
            and re.search(r'\b(?:arquivos?|files?)\b|\.txt\b', goal, re.I)
            and re.search(r'\b(?:soma|some|somar|sum)\b', goal, re.I)
            and not re.search(r'\b(?:salv\w*|escrev\w*|envi\w*|pesquis\w*|subtra\w*|multipli\w*|divid\w*|média|media|produto|diferença)\b', goal, re.I))


def number(value):
    if isinstance(value, bool) or len(str(value)) > 128:
        return None
    try:
        result = Decimal(str(value).strip())
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def observed_values(steps):
    files = {}
    for step in steps:
        if step['tool'] == 'read_file' and step['ok'] and step['verified']:
            value = number(step.get('output', ''))
            if value is None:
                return None
            path = step.get('resolved_path') or step.get('params', {}).get('path')
            if not isinstance(path, str) or not path.strip():
                return None
            path = ntpath.normcase(ntpath.normpath(path))
            files[path] = value
    return list(files.values())


def calculator_issue(goal, steps, tool, params):
    if not file_sum_goal(goal) or tool != 'calculator':
        return None
    if params.get('operation', 'sum') != 'sum':
        return 'O pedido é de soma dos arquivos. Use operation=sum com os valores observados.'
    expected = observed_values(steps)
    values = params.get('values')
    if not expected or not isinstance(values, list):
        return None
    actual = [number(value) for value in values]
    if Counter(actual) != Counter(expected):
        return ('Os operandos não correspondem às leituras verificadas, contando cada caminho uma vez. '
                'Use os valores observados diretamente, sem somar novamente um subtotal ou duplicar um arquivo: '
                + ', '.join(str(value) for value in expected))
    return None


def source_issue(goal, steps, tool, params):
    if not file_sum_goal(goal) or tool != 'read_file' or not isinstance(params.get('path'), str):
        return None
    match = re.search(r'([\w./\\-]*[A-Za-z_-])(\d+)(\.[A-Za-z0-9]+)\s+(?:até|ate|through|to)\s+([\w./\\-]*[A-Za-z_-])(\d+)(\.[A-Za-z0-9]+)', goal, re.I)
    if not match:
        return None
    prefix, first, suffix, second_prefix, last, second_suffix = match.groups()
    if prefix.casefold() != second_prefix.casefold() or suffix.casefold() != second_suffix.casefold():
        return None
    start, end = int(first), int(last)
    if not 0 <= end - start < 64 or first.startswith('0') or last.startswith('0'):
        return None
    names = {ntpath.basename(f'{prefix}{i}{suffix}').casefold() for i in range(start, end + 1)}
    if ntpath.basename(params['path']).casefold() not in names:
        return ('A leitura proposta está fora do intervalo de arquivos solicitado. '
                'Leia somente itens pendentes desse intervalo; se todos já foram lidos e somados, '
                'responda com none e entregue os valores e a soma observada, sem abrir outro arquivo.')
    return None


def final_sum_issue(goal, steps, response):
    if not file_sum_goal(goal) or response.action.type != 'none':
        return None
    claims = re.findall(r'\b(?:soma(?:\s+total)?|total|resultado)(?:\s+(?:é|e|foi|de|igual|a))*\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)',
                        response.speech_output, re.I)
    last_sum = next((s for s in reversed(steps) if s['tool'] == 'calculator'
                     and s['ok'] and s['verified'] and s.get('params', {}).get('operation', 'sum') == 'sum'), None)
    if not last_sum:
        if (claims and observed_values(steps)
                and re.search(r'\b(?:use|usar|utiliz\w*)\s+(?:(?:a|o)\s+)?(?:calculator|calculadora)\b', goal, re.I)):
            return ('O pedido exige usar calculator e ainda não existe soma verificada dessa ferramenta. '
                    'Execute calculator com os valores lidos antes de entregar o total; não some mentalmente.')
        return None
    issue = calculator_issue(goal, steps, 'calculator', last_sum['params'])
    if issue:
        return issue
    # Calculator output is structured data; do not trust numbers in its prose.
    import json
    try:
        expected = number(last_sum['calculation_result'] if 'calculation_result' in last_sum
                          else json.loads(last_sum['output'])['result'])
    except (ValueError, KeyError, TypeError):
        return None
    if expected is None:
        return None
    if any(number(claim.replace(',', '.')) != expected for claim in claims):
        return f'A resposta contradiz a calculadora: a soma observada é {expected}. Corrija a conclusão sem novas ações.'
    return None
