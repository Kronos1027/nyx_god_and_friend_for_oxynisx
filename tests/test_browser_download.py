import base64
from types import SimpleNamespace

import pytest

from tools.browser_download import download_target, save_browser_resource
from tools.browser_errors import BrowserError
from tools.browser_tool import requires_external_confirmation


@pytest.mark.parametrize('value', ['../escape.txt',None])
def test_download_path_must_stay_in_workspace(tmp_path,value):
    with pytest.raises(BrowserError):
        download_target(value,[tmp_path])


def test_download_never_overwrites_existing_file(tmp_path):
    path = tmp_path/'keep.txt'
    path.write_text('user data')
    with pytest.raises(BrowserError,match='já existe'):
        download_target(path,[tmp_path])
    assert path.read_text()=='user data'
    assert requires_external_confirmation({'action':'download'})


class Resource:
    timeout = 3
    control = SimpleNamespace(check=lambda:None)

    def __init__(self,payload=b'Nyx\x00\xff',length=None):
        self.payload,self.length,self.closed = payload,length,False
    def start(self):
        pass
    def status(self):
        return {'url':'https://example.test/page'}
    def _call(self,method,params=None):
        if method=='Page.getFrameTree':
            return {'frameTree':{'frame':{'id':'root'}}}
        if method=='Network.loadNetworkResource':
            return {'resource':{'success':True,'httpStatusCode':200,'stream':'handle',
                'headers':{'Content-Length':str(len(self.payload) if self.length is None else self.length)}}}
        if method=='IO.read':
            return {'data':base64.b64encode(self.payload).decode(),'base64Encoded':True,'eof':True}
        if method=='IO.close':
            self.closed=True
            return {}
        pytest.fail(method)


def test_binary_download_and_exclusive_publication(tmp_path):
    resource = Resource()
    path = download_target('exact.bin',[tmp_path])
    result = save_browser_resource(resource,'https://example.test/file',path)
    assert result['verified'] and path.read_bytes()==resource.payload and resource.closed
    assert not list(tmp_path.glob('*.part'))
    with pytest.raises(FileExistsError):
        save_browser_resource(Resource(), 'https://example.test/file',path)
    assert path.read_bytes()==resource.payload


def test_incomplete_response_does_not_publish_partial_target(tmp_path):
    resource = Resource(length=100)
    target = tmp_path/'incomplete.bin'
    with pytest.raises(BrowserError,match='incompleto'):
        save_browser_resource(resource,'https://example.test/file',target)
    assert not target.exists() and resource.closed and not list(tmp_path.iterdir())


def test_download_origin_must_be_current_browser_origin(tmp_path):
    with pytest.raises(BrowserError,match='mesma origem'):
        save_browser_resource(Resource(),'https://other.test/file',tmp_path/'no.bin')
    assert not list(tmp_path.iterdir())


def test_oversized_header_refused_before_local_file_creation(tmp_path):
    with pytest.raises(BrowserError,match='50MiB'):
        save_browser_resource(Resource(length=100*1024**2),'https://example.test/file',tmp_path/'no.bin')
    assert not list(tmp_path.iterdir())
