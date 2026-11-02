"""Bounded CDP accessibility snapshots with document-bound, expiring refs."""
import time
from uuid import uuid4

from tools.browser_errors import BrowserError

MAX_AX_NODES = 150
MAX_AX_FRAMES = 8
REF_TTL_SECONDS = 30


def frame_inventory(tree):
    frames, pending = {}, [tree.get('frameTree', {})]
    while pending:
        item = pending.pop(0)
        frame = item.get('frame', {})
        if frame.get('id'):
            frames[frame['id']] = frame
        pending.extend(item.get('childFrames', []))
    return frames


def ax_identity(node):
    return (str(node.get('role', {}).get('value', '')),
            str(node.get('name', {}).get('value', '')))


class AccessibilitySnapshot:
    def __init__(self, session, clock=time.monotonic):
        self.session = session
        self.clock = clock
        self.invalidate()

    def invalidate(self):
        self.snapshot = None
        self.refs = {}
        self.created = 0
        self.frames = {}
        self.root_frame = None
        self.connection = None

    def capture(self):
        self.invalidate()
        frames = frame_inventory(self.session._call('Page.getFrameTree'))
        self.session._call('Accessibility.enable')
        output, errors, seen = [], [], set()
        truncated = len(frames) > MAX_AX_FRAMES
        for frame_id, _frame in list(frames.items())[:MAX_AX_FRAMES]:
            try:
                nodes = self.session._call('Accessibility.getFullAXTree', {'frameId':frame_id, 'depth':8}).get('nodes', [])
            except BrowserError as exc:
                errors.append({'frame':frame_id, 'error_code':exc.code,
                               'message':'Árvore deste frame indisponível neste transporte.'})
                continue
            refs_by_node, frame_rows = {}, []
            for node in nodes:
                if node.get('ignored'):
                    continue
                backend = node.get('backendDOMNodeId')
                if type(backend) is not int or backend in seen:
                    continue
                if len(output) >= MAX_AX_NODES:
                    truncated = True
                    break
                try:
                    dom = self.session._call('DOM.describeNode', {'backendNodeId':backend}).get('node', {})
                except BrowserError:
                    continue
                attributes = dom.get('attributes', [])
                attrs = dict(zip(attributes[::2], attributes[1::2], strict=True))
                protected = attrs.get('type', '').casefold() == 'password'
                role, name = ax_identity(node)
                ref = 'e'+str(len(self.refs)+1)
                self.refs[ref] = {'backend':backend, 'frame':frame_id, 'identity':(role,name),
                                  'protected':protected, 'tag':dom.get('nodeName'),
                                  'href':attrs.get('href'), 'type':attrs.get('type')}
                seen.add(backend)
                refs_by_node[node['nodeId']] = ref
                states = {p['name']:p.get('value', {}).get('value') for p in node.get('properties', [])
                          if p.get('name') in {'disabled','checked','expanded','selected','pressed','required'}}
                row = {'ref':ref, 'role':role, 'name':'[campo protegido]' if protected else name[:160],
                       'frame':frame_id, 'protected':protected, 'actionable':dom.get('nodeType') == 1, 'states':states}
                output.append(row)
                frame_rows.append((node,row))
            for node,row in frame_rows:
                row['parent_ref'] = refs_by_node.get(node.get('parentId'))
        self.snapshot = uuid4().hex
        self.created = self.clock()
        self.connection = self.session._ws_url
        self.frames = {key:frame.get('loaderId') for key,frame in frames.items()}
        self.root_frame = next(iter(frames),None)
        output.sort(key=lambda row: (not row['actionable'], row['role'] in {'generic','RootWebArea'}))
        return {'snapshot':self.snapshot, 'expires_seconds':REF_TTL_SECONDS,
                'tree':output, 'truncated':truncated, 'frame_errors':errors,
                'scope':'CDP Accessibility, profundidade8, até150nós e8frames; sem valores de campos.'}

    def resolve(self, locator):
        def stale():
            return BrowserError('Referência antiga ou alterada; inspecione a página novamente.', 'ELEMENT_STALE')
        if (not self.snapshot or locator['snapshot'] != self.snapshot or self.clock()-self.created > REF_TTL_SECONDS
                or self.connection != self.session._ws_url or locator['ref'] not in self.refs):
            raise stale()
        entry = self.refs[locator['ref']]
        if entry['protected']:
            raise BrowserError('Campo protegido; use entrada humana no navegador.', 'PERMISSION')
        frames = frame_inventory(self.session._call('Page.getFrameTree'))
        relevant = {entry['frame'], self.root_frame}
        if any(key not in frames or frames[key].get('loaderId') != self.frames.get(key) for key in relevant):
            raise stale()
        try:
            nodes = self.session._call('Accessibility.getPartialAXTree',
                {'backendNodeId':entry['backend'], 'fetchRelatives':False}).get('nodes', [])
            node = next((node for node in nodes if node.get('backendDOMNodeId') == entry['backend'] and not node.get('ignored')), None)
            dom = self.session._call('DOM.describeNode', {'backendNodeId':entry['backend']}).get('node', {})
            attributes = dom.get('attributes', [])
            attrs = dict(zip(attributes[::2], attributes[1::2], strict=True))
            if (node is None or ax_identity(node) != entry['identity'] or dom.get('nodeName') != entry['tag']
                    or attrs.get('href') != entry['href'] or attrs.get('type') != entry['type']):
                raise stale()
            resolved = self.session._call('DOM.resolveNode', {'backendNodeId':entry['backend']})
            object_id = resolved.get('object', {}).get('objectId')
            if not object_id:
                raise stale()
            return object_id
        except BrowserError as exc:
            if exc.code in {'ELEMENT_STALE','PERMISSION'}:
                raise
            raise stale() from exc
