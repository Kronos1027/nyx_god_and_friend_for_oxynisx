"""Bounded, structured provenance for data actually returned by web transports."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlsplit, urlunsplit


def source_url(value: str) -> str:
    """Allow only explicit HTTP(S) URLs without credentials or hidden separators."""
    if not isinstance(value, str) or not value or len(value) > 4000:
        raise ValueError('Informe uma URL HTTP ou HTTPS válida, com até 4000 caracteres.')
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('A URL contém espaços ou caracteres de controle; use uma URL codificada.')
    parts = urlsplit(value)
    if (parts.scheme.lower() not in {'http', 'https'} or not parts.hostname
            or parts.username is not None or parts.password is not None or '\\' in value):
        raise ValueError('Somente URLs HTTP(S) sem credenciais são permitidas.')
    # Accessing .port also validates malformed/out-of-range port components.
    port = parts.port
    host = parts.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    if port is not None and (parts.scheme.lower(), port) not in {('http', 80), ('https', 443)}:
        host += ':' + str(port)
    return urlunsplit((parts.scheme.lower(), host, parts.path or '/', parts.query, parts.fragment))


def consulted_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def source_record(title: str, url: str, *, kind='page', status='read',
                  retrieved_at: str | None = None, chars: int = 0) -> dict:
    if kind not in {'page', 'api', 'search_result'} or status not in {'read', 'discovered'}:
        raise ValueError('Tipo de proveniência inválido.')
    if (kind == 'search_result') != (status == 'discovered'):
        raise ValueError('Resultado de busca é descoberta, não leitura da página de destino.')
    url = source_url(url)
    title = re.sub(r'[\x00-\x1f\x7f]', ' ', str(title))
    title = re.sub(r'\s+', ' ', title).strip()[:240] or urlsplit(url).hostname
    return {'title': title, 'url': url, 'retrieved_at': retrieved_at or consulted_at(),
            'kind': kind, 'status': status, 'chars': max(0, int(chars))}


def valid_source(value) -> dict | None:
    """Validate engine metadata; this does not turn page text into trusted policy."""
    if not isinstance(value, dict):
        return None
    try:
        title, stamp = value['title'], value['retrieved_at']
        if not isinstance(title, str) or not title.strip() or len(title) > 240:
            return None
        if not isinstance(stamp, str) or len(stamp) > 50:
            return None
        date = datetime.fromisoformat(stamp)
        if date.tzinfo is None or date.utcoffset() is None:
            return None
        if type(value.get('chars')) is not int or value['chars'] < 0:
            return None
        return source_record(title, value['url'], retrieved_at=stamp, kind=value['kind'],
                             status=value['status'], chars=value['chars'])
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def source_header(source: dict) -> str:
    state = 'página lida' if source['status'] == 'read' else 'resultado de busca; destino ainda não lido'
    return (f"Título: {source['title']}\nURL: {source['url']}\n"
            f"Consulta UTC: {source['retrieved_at']}\nEscopo: {state}.")
