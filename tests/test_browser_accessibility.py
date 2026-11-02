import pytest

from tools.browser_accessibility import AccessibilitySnapshot
from tools.browser_errors import BrowserError


class AXFixture:
    _ws_url = 'ws://owned/tab1'
    def __init__(self):
        self.loader = 'main-v1'
        self.ad_loader = 'ad-v1'
        self.methods = []
    def _call(self, method, params=None):
        self.methods.append(method)
        node = {'nodeId':'1','backendDOMNodeId':1,'role':{'value':'button'},'name':{'value':'Fixture'}}
        if method == 'Page.getFrameTree':
            return {'frameTree':{'frame':{'id':'main','loaderId':self.loader},
                    'childFrames':[{'frame':{'id':'ad','loaderId':self.ad_loader}}]}}
        if method == 'Accessibility.getFullAXTree':
            return {'nodes':[node] if params['frameId']=='main' else []}
        if method == 'Accessibility.getPartialAXTree':
            return {'nodes':[node]}
        if method == 'DOM.describeNode':
            return {'node':{'nodeType':1,'nodeName':'BUTTON','attributes':[]}}
        if method == 'DOM.resolveNode':
            return {'object':{'objectId':'owned-node'}}
        return {}


def test_refs_expire_without_dispatch_and_ignore_unrelated_frame_changes():
    browser, clock = AXFixture(), [10]
    snapshot = AccessibilitySnapshot(browser, clock=lambda:clock[0])
    info = snapshot.capture()
    locator = {'ref':'e1','snapshot':info['snapshot']}
    browser.ad_loader = 'ad-v2'
    assert snapshot.resolve(locator) == 'owned-node'
    clock[0] += 31
    with pytest.raises(BrowserError) as expired:
        snapshot.resolve(locator)
    assert expired.value.code == 'ELEMENT_STALE'
    assert not any(method.startswith('Input.') for method in browser.methods)


@pytest.mark.parametrize('changed', ['loader','tab'])
def test_document_or_tab_change_invalidates_reference(changed):
    browser = AXFixture()
    snapshot = AccessibilitySnapshot(browser)
    info = snapshot.capture()
    if changed == 'loader':
        browser.loader = 'main-v2'
    else:
        browser._ws_url = 'ws://owned/tab2'
    with pytest.raises(BrowserError) as stale:
        snapshot.resolve({'ref':'e1','snapshot':info['snapshot']})
    assert stale.value.code == 'ELEMENT_STALE'
