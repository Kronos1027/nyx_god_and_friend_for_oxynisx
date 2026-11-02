"""Text-only HTTP reads: bounded bytes, explicit redirects and no session cookies."""
from __future__ import annotations

from html.parser import HTMLParser
import re
import time
import urllib.request

from core.operation_control import OperationControl
from tools.web_sources import source_url

MAX_RESPONSE_BYTES = 1024 * 1024


class WebReadError(ValueError):
    def __init__(self, message, code='UNVERIFIED', suggestions=()):
        super().__init__(message)
        self.code = code
        self.suggestions = list(suggestions)


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            target = source_url(newurl)
        except ValueError as exc:
            raise WebReadError('O redirecionamento saiu de HTTP(S) ou incluiu credenciais.',
                               'BLOCKED_POLICY', ['Use o endereço HTTP(S) público da fonte.']) from exc
        return super().redirect_request(req, fp, code, msg, headers, target)


def open_url(request, *, timeout):
    # A dedicated opener never inherits an installed cookie/authentication handler.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Redirects())
    return opener.open(request, timeout=timeout)


def read_text_url(url, *, timeout, user_agent, control=None):
    try:
        url = source_url(url)
    except ValueError as exc:
        raise WebReadError(str(exc), 'BLOCKED_POLICY', ['Informe uma URL HTTP(S) sem senha ou usuário.']) from exc
    control = control or OperationControl()
    control.check()
    started = time.monotonic()
    request = urllib.request.Request(url, headers={
        'User-Agent': user_agent, 'Accept': 'text/html,application/xhtml+xml,text/plain,application/json',
        'Accept-Encoding': 'identity'})
    with open_url(request, timeout=timeout) as response:
        final_url = source_url(response.geturl())
        content_type = response.headers.get_content_type()
        if content_type not in {'text/html', 'application/xhtml+xml', 'text/plain', 'application/json'}:
            raise WebReadError('A fonte não retornou HTML, texto ou JSON legível.',
                               suggestions=['Use a página textual da fonte; não um arquivo binário.'])
        if response.headers.get('Content-Encoding', 'identity').strip().lower() not in {'', 'identity'}:
            raise WebReadError('A fonte ignorou a solicitação de texto sem compressão.',
                               suggestions=['Tente outra página da fonte.'])
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_RESPONSE_BYTES:
            raise WebReadError('A página excede o limite de leitura de 1 MiB.',
                               suggestions=['Leia uma página menor ou uma seção específica.'])
        chunks, size = [], 0
        while True:
            control.check()
            if time.monotonic() - started >= timeout:
                raise TimeoutError('A leitura ultrapassou o prazo.')
            data = response.read(min(16384, MAX_RESPONSE_BYTES - size + 1))
            if not data:
                break
            size += len(data)
            if size > MAX_RESPONSE_BYTES:
                raise WebReadError('A página excede o limite de leitura de 1 MiB.',
                                   suggestions=['Leia uma página menor ou uma seção específica.'])
            chunks.append(data)
        if length and size != int(length):
            raise WebReadError('A leitura terminou antes do tamanho declarado pela fonte.',
                               suggestions=['Tente novamente; não use o trecho incompleto como resposta.'])
        text = b''.join(chunks).decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
    return {'url': final_url, 'text': text, 'content_type': content_type, 'bytes': size}


class HTMLTextExtractor(HTMLParser):
    """Separate title/body/main and omit executable or navigation-only fragments."""
    _HIDDEN = {'script', 'style', 'head', 'noscript', 'template', 'svg', 'nav', 'header', 'footer'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.result, self.main_parts, self.title_parts = [], [], []
        self._hidden = []
        self._title = False
        self._main = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self._title = True
        if tag == 'main':
            self._main += 1
        if tag in self._HIDDEN:
            self._hidden.append(tag)

    def handle_endtag(self, tag):
        if tag == 'title':
            self._title = False
        if tag == 'main':
            self._main = max(0, self._main - 1)
        if tag in self._hidden:
            # Closing an outer ignored element also closes malformed inner tags.
            index = len(self._hidden) - 1 - self._hidden[::-1].index(tag)
            del self._hidden[index:]

    def handle_data(self, data):
        cleaned = re.sub(r'\s+', ' ', data).strip()
        if not cleaned:
            return
        if self._title:
            self.title_parts.append(cleaned)
        if not self._hidden:
            self.result.append(cleaned)
            if self._main:
                self.main_parts.append(cleaned)

    def get_text(self):
        return ' '.join(self.main_parts or self.result)

    def get_title(self):
        return ' '.join(self.title_parts)[:240]


def extract_document(document):
    if document['content_type'] in {'text/html', 'application/xhtml+xml'}:
        extractor = HTMLTextExtractor()
        extractor.feed(document['text'])
        extractor.close()
        title, text = extractor.get_title(), extractor.get_text()
        if re.search(r'^(?:just a moment|access denied|attention required|verify (?:you|your)|captcha)\b', title, re.I):
            raise WebReadError('A fonte exibiu uma verificação de acesso, não o conteúdo pedido.',
                               suggestions=['Abra a fonte no navegador visível ou tente outra fonte.'])
    else:
        title, text = '', document['text'].strip()
    if not text:
        raise WebReadError('A página não contém texto legível; não obtive uma fonte para responder.',
                           suggestions=['Tente outra fonte ou abra a página no navegador visível.'])
    return title, text
