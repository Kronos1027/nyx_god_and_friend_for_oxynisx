"""Owned HTTP world for all ten acceptance scenarios; no production imports."""
from contextlib import contextmanager
import http.server
import io
import json
import threading
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import wave


class BrowserFixture:
    def __init__(self, number, run):
        self.number, self.run = number, run
        self.marker = f'NYX-{run}-{uuid4().hex[:8]}'
        self.value = f'Nyx ação {run}'
        self.code = str(4100 + run * 37 + number)
        self.events, self.requests = [], []
        self.file_bytes = ('Arquivo Nyx de teste\n' + self.marker + '\n').encode()
        self.base = ''

    def page(self, title, body, script=''):
        return (f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{title}</title>'
            '<style>body{font:18px system-ui;margin:30px}label,input,button,select{display:block;margin:14px}table,td,th{border:1px solid;padding:12px}</style>'
            f'<body><h1>{title}</h1>{body}<script>{script}</script></body></html>').encode()

    def respond(self, path, query, cookie):
        if path == '/file.txt':
            return self.file_bytes, 'application/octet-stream', {}
        if path == '/tone.wav':
            data = io.BytesIO()
            with wave.open(data,'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b'\0\0' * 8000 * 15)
            return data.getvalue(), 'audio/wav', {}
        if path == '/inner':
            return self.page('Cadastro no iframe', '<label>Destino iframe<input id="destino"></label>',
                "window.trustedInput=false;destino.oninput=e=>window.trustedInput=e.isTrusted"), 'text/html; charset=utf-8', {}
        if path == '/result/2':
            body = f'<p>Segundo resultado: código {self.code}</p>'
            return self.page('Segundo resultado Nyx',body),'text/html; charset=utf-8',{}
        if path == '/result/1':
            return self.page('Primeiro resultado Nyx','<p>Este não é o segundo resultado.</p>'),'text/html; charset=utf-8',{}
        if path.startswith('/tab/'):
            name = 'Origem' if path.endswith('origin') else 'Destino'
            return self.page(name+' Nyx',f'<p>Código da aba {name}: {self.code if name=="Origem" else "0000"}</p>'),'text/html; charset=utf-8',{}
        if path.startswith('/session'):
            active = 'nyx_fixture_session='+self.marker in cookie
            seed = path.endswith('/seed')
            body = '<p id="session">Sessão local de teste ativa</p>' if active or seed else '<p id="session">Sem sessão local de teste</p>'
            body += '<p>Esta sessão descartável não usa uma conta pessoal nem senha.</p>'
            headers = {'Set-Cookie':f'nyx_fixture_session={self.marker}; Max-Age=3600; Path=/; HttpOnly; SameSite=Strict'} if seed else {}
            return self.page('Sessão local Nyx',body),'text/html; charset=utf-8',headers
        number, script = self.number, ''
        if number == 1:
            body = f'<p>Página Nyx pronta. Código {self.code}</p>'
        elif number == 2:
            body = '<form method="get"><label>Pesquisar<input id="query" name="q"></label><button>Buscar</button></form>'
            if query.get('q') == ['Nyx']:
                body += '<ol><li><a href="/result/1">Primeiro resultado</a></li><li><a href="/result/2">Segundo resultado</a></li></ol>'
        elif number == 3:
            body = f'<table><thead><tr><th>Item</th><th>Quantidade</th></tr></thead><tbody><tr><td>Saturno</td><td>{self.code}</td></tr><tr><td>Vênus</td><td>{int(self.code)+19}</td></tr></tbody></table>'
        elif number == 4:
            body = '<form id="form"><label>Nome<input id="nome" name="nome"></label><label>Mensagem<input id="mensagem" name="mensagem"></label><button>Salvar cadastro local</button></form><p id="result"></p>'
            script = """document.querySelector('form').onsubmit=async e=>{e.preventDefault();
                const data={name:nome.value,message:mensagem.value,trusted:e.isTrusted};
                await fetch('/event',{method:'POST',body:JSON.stringify(data)});result.textContent='Cadastro local salvo';};"""
        elif number == 5:
            body = '<p>O cadastro está no quadro abaixo.</p><iframe id="frame-cadastro" title="Cadastro" src="/inner" width="600" height="280"></iframe>'
        elif number == 6:
            body = '<div id="widget"></div>'
            script = """const root=widget.attachShadow({mode:'open'});root.innerHTML='<label>Nome da sombra<input id="nome"></label>';
                window.trustedInput=false;root.querySelector('input').oninput=e=>window.trustedInput=e.isTrusted;"""
        elif number == 8:
            body = '<a href="/file.txt" download="fixture.txt">Baixar arquivo de teste</a>'
        elif number == 9:
            body = '<audio id="audio" src="/tone.wav" preload="auto" loop></audio><button id="play">Reproduzir</button><button id="pause">Pausar</button><p id="state">Parada</p>'
            script = """audio.volume=.01;play.onclick=async()=>{await audio.play();state.textContent='Reproduzindo';};
                pause.onclick=()=>{audio.pause();state.textContent='Pausada';};"""
        else:
            body = '<p>Fixture de navegador</p>'
        return self.page('Fixture Nyx '+str(number),body,script),'text/html; charset=utf-8',{}

    @contextmanager
    def serve(self):
        fixture = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                parsed = urlsplit(self.path)
                fixture.requests.append({'path':parsed.path,'query':parse_qs(parsed.query),
                    'session_present':'nyx_fixture_session='+fixture.marker in self.headers.get('Cookie','')})
                data, content_type, headers = fixture.respond(parsed.path,parse_qs(parsed.query),self.headers.get('Cookie',''))
                self.send_response(200)
                self.send_header('Content-Type',content_type)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                for key,value in headers.items():
                    self.send_header(key,value)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError):
                    pass
            def do_POST(self):  # noqa: N802
                size = int(self.headers.get('Content-Length','0'))
                if self.path != '/event' or not 0 < size <= 4096:
                    self.send_error(400)
                    return
                fixture.events.append(json.loads(self.rfile.read(size)))
                self.send_response(204)
                self.end_headers()
            def log_message(self,*args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.base = f'http://127.0.0.1:{server.server_port}'
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            yield self
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def prompt(self, download):
        base = self.base
        goals = {
            1:f'Abra {base}/ e informe o código da página.',
            2:f'Na página {base}/ pesquise Nyx no formulário, abra o segundo resultado e informe seu código.',
            3:f'Leia a tabela de {base}/ e informe os dois itens e suas quantidades exatas.',
            4:f'Abra {base}/, preencha Nome com {self.value} e Mensagem com Olá mundo, e salve o cadastro local pelo botão.',
            5:f'Abra {base}/ e preencha o campo Destino iframe, dentro do quadro Cadastro, com {self.value}.',
            6:f'Abra {base}/ e preencha o campo Nome da sombra do componente com {self.value}.',
            7:'Troque para a aba Origem Nyx já aberta e informe seu código. Não crie outra aba.',
            8:f'Abra {base}/ e baixe o arquivo do link para {download}. Não execute o arquivo.',
            9:f'Abra {base}/, reproduza a mídia de teste, confira que está tocando e depois pause. Informe o estado final observado.',
            10:f'Reabra {base}/session e confira se a sessão local de teste persistiu após o navegador ter sido encerrado. Informe o estado observado.'}
        return goals[self.number]
