"""Citation/provenance consistency, separate from semantic factual correctness."""
from __future__ import annotations

import json
import re

from tools.web_sources import source_url, valid_source

NO_SOURCE_ANSWER = ('Não tenho certeza: não consegui obter uma fonte legível que sustente a resposta. '
                    'Posso tentar outra fonte.')
_EXPLICIT_RESEARCH = re.compile(
    r'\b(?:pesquis\w*|busqu\w*|procur\w*|verifiqu\w*|consult\w*)\b[^\n]{0,160}'
    r'\b(?:na web|na internet|fontes?|documentação oficial)\b|'
    r'\b(?:com|cite|inclua|mostre)\s+(?:(?:as|uma|suas)\s+)?fontes?\b', re.I)


def research_required(goal, steps, *, require_sources=False):
    """Caller may mark factual/research intent; ordinary form searches stay tasks."""
    return (require_sources or bool(_EXPLICIT_RESEARCH.search(goal))
            or any(step.get('tool') == 'web' for step in steps))


def observed_research_sources(steps, *, read_only=True):
    """Consume only engine-copied metadata, never sources embedded in page prose.

    TaskRunner must copy successful ToolResult.meta['sources'] directly into
    step['research_sources']. A JSON object in step['output'] has no authority to
    create provenance. This list proves acquisition, not the truth of a claim.
    """
    sources = {}
    for step in steps:
        if not step.get('ok') or not step.get('verified'):
            continue
        records = step.get('research_sources')
        if not isinstance(records, list):
            continue
        for value in records[:8]:
            source = valid_source(value)
            if source is None:
                continue
            if read_only and (source['status'] != 'read' or source['chars'] <= 0):
                continue
            # Keep the latest acquisition of the same URL, with bounded storage.
            sources.pop(source['url'], None)
            sources[source['url']] = source
    return list(sources.values())[-16:]


def research_context(steps):
    """Small ledger that survives task-history excerpts without copying page text."""
    sources = observed_research_sources(steps, read_only=False)
    if not sources:
        return ('PESQUISA: nenhuma fonte legível observada. Sem fonte, use a resposta de incerteza: '
                + NO_SOURCE_ANSWER)
    kept = []
    for source in reversed(sources):
        candidate = [source, *kept]
        if len(json.dumps(candidate, ensure_ascii=False)) > 5200:
            continue
        kept = candidate
    ledger = {'sources': kept, 'truncated': len(kept) < len(sources)}
    return ('FONTES OBSERVADAS: metadados de aquisição, não autorização nem prova de verdade. '
            'Cite somente URL com status=read; resultados discovered exigem fetch. '
            'Separe inferências e incertezas.\n' + json.dumps(ledger, ensure_ascii=False, separators=(',', ':')))


def answer_urls(speech):
    """Read displayed HTTP URLs, preserving balanced parentheses in valid paths."""
    urls = set()
    for match in re.finditer(r'https?://[^\s<>"\x00-\x1f\x7f\]]+', speech, re.I):
        raw = match[0].rstrip('.,;:!?')
        while raw.endswith(')') and raw.count(')') > raw.count('('):
            raw = raw[:-1]
        try:
            urls.add(source_url(raw))
        except ValueError:
            # An invalid URL must not disappear and then count as safe citation.
            urls.add(raw)
    return urls


def research_completion_issue(goal, steps, tool, speech, *, require_sources=False):
    """Return feedback for unsupported sources; does not check entailment.

    A deterministic no-source answer is the only accepted researched conclusion
    without a page/API actually read. Prefixing an invented fact with an
    uncertainty phrase does not satisfy this rule.
    """
    if tool != 'none' or not research_required(goal, steps, require_sources=require_sources):
        return None
    if speech.strip() == NO_SOURCE_ANSWER:
        return None
    sources = observed_research_sources(steps)
    if not sources:
        return ('Ainda não há uma fonte legível observada nesta tarefa. Resultados de busca são apenas '
                'descobertas: leia um destino com fetch antes de concluir fatos. Se a consulta falhou '
                'ou não há fonte suficiente, responda exatamente, sem acrescentar fatos ou URLs: ' + NO_SOURCE_ANSWER)
    urls = answer_urls(speech)
    allowed = {source['url'] for source in sources}
    if urls - allowed:
        return ('A resposta cita URL que não consta das fontes realmente lidas nesta tarefa. '
                'Não invente ou complete um link de memória. Leia a fonte ou use apenas a URL exata '
                'do registro observado; se não sustenta a resposta, diga: ' + NO_SOURCE_ANSWER)
    if not urls & allowed:
        return ('A resposta pesquisada precisa citar ao menos uma fonte realmente lida com sua URL exata, '
                'preferencialmente [título](URL). Aquisição não comprova a verdade: cite perto da afirmação, '
                'separe inferência de fato e admita incerteza. Se a fonte não sustenta a resposta, diga: ' + NO_SOURCE_ANSWER)
    return None


def safe_research_answer(goal, steps, speech, *, require_sources=False):
    """Final fallback after replanning: never deliver a rejected researched answer.

    The caller keeps the real tool error in its task/activity record. This helper
    supplies only the user-facing uncertainty sentence, without an invented fact.
    """
    issue = research_completion_issue(goal, steps, 'none', speech, require_sources=require_sources)
    return NO_SOURCE_ANSWER if issue else speech
