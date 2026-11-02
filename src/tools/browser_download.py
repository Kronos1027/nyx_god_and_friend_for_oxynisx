"""Explicit bounded downloads through the owned browser's network session."""
import base64
import hashlib
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit

from tools.browser_errors import BrowserError
from tools.browser_profile import _redirected

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024


def download_target(value, roots):
    if not value or not roots:
        raise BrowserError('Informe o arquivo de destino em uma pasta permitida.', 'BLOCKED_POLICY')
    target = Path(str(value))
    if not target.is_absolute():
        target = roots[0] / target
    if any(_redirected(part) for part in (target, *target.parents)):
        raise BrowserError('Destino de download não pode atravessar links ou junctions.', 'BLOCKED_POLICY')
    target = target.resolve()
    if not any(root in target.parents for root in roots):
        raise BrowserError('Download fora das pastas permitidas.', 'BLOCKED_POLICY')
    if target.exists():
        raise BrowserError('O arquivo de destino já existe; escolha outro nome. Nada foi sobrescrito.', 'AMBIGUOUS')
    return target


def save_browser_resource(session, url, target):
    from tools.browser_tool import validate_url
    url = validate_url(url)
    session.start()
    current = session.status().get('url', '')
    def origin(value):
        parsed = urlsplit(value)
        return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme=='https' else 80)
    if origin(url) != origin(current):
        raise BrowserError('Abra primeiro a página da mesma origem do arquivo e confirme o download.', 'BLOCKED_POLICY')
    frame = session._call('Page.getFrameTree')['frameTree']['frame']['id']
    resource = session._call('Network.loadNetworkResource', {'frameId':frame, 'url':url,
        'options':{'disableCache':True,'includeCredentials':True}}).get('resource', {})
    handle, stage = resource.get('stream'), None
    try:
        if not resource.get('success') or not 200 <= resource.get('httpStatusCode',0) < 300 or not handle:
            raise BrowserError('O navegador não confirmou uma resposta HTTP de arquivo completa.', 'UNVERIFIED')
        headers = {key.lower():str(value) for key,value in resource.get('headers',{}).items()}
        if headers.get('content-type','').lower().startswith('text/html') and target.suffix.lower() not in {'.html','.htm'}:
            raise BrowserError('A URL retornou uma página HTML, não o arquivo solicitado. Confira o link e a sessão antes de tentar outro download.', 'UNVERIFIED')
        length = headers.get('content-length')
        if length is not None and (not length.isdecimal() or int(length) > MAX_DOWNLOAD_BYTES):
            raise BrowserError('Tamanho do download inválido ou superior ao limite de50MiB.', 'BLOCKED_POLICY')
        target.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        deadline = time.monotonic() + session.timeout
        with tempfile.NamedTemporaryFile(prefix='.nyx-download-', suffix='.part', dir=target.parent, delete=False) as output:
            stage = Path(output.name)
            while True:
                session.control.check()
                if time.monotonic() >= deadline:
                    raise BrowserError('Download não terminou no prazo; destino final não publicado.', 'TIMEOUT')
                packet = session._call('IO.read', {'handle':handle,'size':65536})
                data = packet.get('data','')
                data = base64.b64decode(data,validate=True) if packet.get('base64Encoded') else data.encode('utf-8')
                size += len(data)
                if size > MAX_DOWNLOAD_BYTES:
                    raise BrowserError('Download excedeu50MiB; destino final não publicado.', 'BLOCKED_POLICY')
                output.write(data)
                digest.update(data)
                if packet.get('eof'):
                    break
            output.flush()
            os.fsync(output.fileno())
        if length is not None and size != int(length):
            raise BrowserError('Arquivo recebido está incompleto; destino final não publicado.', 'UNVERIFIED')
        # Hard-link publication is exclusive on Windows and POSIX: never replace
        # a file that appeared after validation. Stage and target share a directory.
        os.link(stage, target, follow_symlinks=False)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if target.stat().st_size != size or actual != digest.hexdigest():
            raise BrowserError('A conferência do arquivo gravado divergiu.', 'UNVERIFIED')
        return {'path':str(target),'bytes':size,'sha256':actual,'verified':True,'check':'download_bytes_on_disk'}
    finally:
        try:
            if handle:
                try:
                    session._call('IO.close', {'handle':handle})
                except RuntimeError:
                    pass  # Cancellation can prevent transport cleanup; session.close owns the browser.
        finally:
            if stage is not None:
                stage.unlink(missing_ok=True)  # Only the exclusively-created staging file.
