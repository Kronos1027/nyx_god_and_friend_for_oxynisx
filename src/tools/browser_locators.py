"""Bounded, explicit DOM scopes and accessibility references. Values stay data."""
import re

MAX_LOCATOR_CHARS = 500


def clean_locator(value):
    if isinstance(value, str):
        value = {"css": value.strip()}
    if not isinstance(value, dict) or set(value) - {"css", "role", "name", "label", "text", "shadow", "frame", "ref", "snapshot"}:
        raise ValueError("Informe seletor CSS ou localizador por role/name, label ou text.")
    if 'ref' in value:
        if set(value) != {'ref','snapshot'}:
            raise ValueError('Referência exige somente ref e snapshot da inspeção atual.')
        ref = 'e'+str(value['ref']) if type(value['ref']) is int else value['ref']
        if not isinstance(ref,str) or not re.fullmatch(r'e[1-9][0-9]{0,4}',ref):
            raise ValueError('Referência inválida; use a ref numerada da inspeção.')
        snapshot = value['snapshot']
        if not isinstance(snapshot,str) or not re.fullmatch(r'[a-f0-9]{32}',snapshot):
            raise ValueError('Snapshot inválido; inspecione a página novamente.')
        return {'ref':ref,'snapshot':snapshot}
    scopes = {}
    for key in ('shadow','frame'):
        if key in value:
            chain = value[key]
            if not isinstance(chain,list) or not 1 <= len(chain) <= 8 or any(
                not isinstance(v,str) or not v.strip() or len(v)>MAX_LOCATOR_CHARS for v in chain):
                raise ValueError(f'Escopo {key} exige uma lista de um a oito seletores CSS explícitos.')
            scopes[key] = [v.strip() for v in chain]
    value = {k:v for k,v in value.items() if k not in scopes}
    keys = set(value) & {"css", "role", "label", "text"}
    if len(keys) != 1 or ("name" in value and "role" not in value):
        raise ValueError("Use exatamente um tipo de localizador.")
    if any(not isinstance(v, str) or not v.strip() or len(v) > MAX_LOCATOR_CHARS for v in value.values()):
        raise ValueError("Localizador vazio ou longo demais.")
    return {**{k: v.strip() for k, v in value.items()}, **scopes}


SCOPE = r"""(locator => {
    let root=document;
    const unique = (scope,selector) => {
        const nodes=scope.querySelectorAll(selector);
        if (nodes.length!==1) throw new Error(nodes.length?'AMBIGUOUS: escopo com múltiplos hosts.':'NOT_FOUND: host do escopo não encontrado.');
        return nodes[0];
    };
    for (const selector of locator.frame || []) {
        const frame=unique(root,selector);
        if (!['IFRAME','FRAME'].includes(frame.tagName) || !frame.contentDocument)
            throw new Error('UNVERIFIED: iframe indisponível ou de outra origem.');
        root=frame.contentDocument;
    }
    for (const selector of locator.shadow || []) {
        const host=unique(root,selector);
        if (!host.shadowRoot || host.shadowRoot.mode!=='open')
            throw new Error('UNVERIFIED: Shadow DOM fechado ou indisponível.');
        root=host.shadowRoot;
    }
    return root;
})"""


RESOLVE = r"""(locator => {
    const root = SCOPE(locator);
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const visible = el => {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility === 'visible' && s.display !== 'none';
    };
    const label = el => Array.from(el.labels || []).map(l => norm(l.textContent)).join(' ');
    const name = el => norm(el.getAttribute('aria-label')) ||
        norm((el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id =>
            el.getRootNode().getElementById(id)?.textContent || '').join(' ')) ||
        label(el) || norm(el.innerText || el.getAttribute('alt') ||
            (['submit', 'button'].includes(el.type) ? el.value : ''));
    const role = el => el.getAttribute('role') || ({BUTTON:'button', A:el.href?'link':'',
        TEXTAREA:'textbox', SELECT:'combobox', IMG:'img'}[el.tagName]) ||
        (el.tagName === 'INPUT' ? ({checkbox:'checkbox', radio:'radio',
            button:'button', submit:'button', range:'slider', number:'spinbutton'}[el.type] || 'textbox') : '');
    let nodes;
    if (locator.css) nodes = Array.from(root.querySelectorAll(locator.css));
    else {
        nodes = Array.from(root.querySelectorAll('*')).filter(el => {
            if (locator.role) return role(el) === locator.role && (!locator.name || name(el) === norm(locator.name));
            if (locator.label) return label(el) === norm(locator.label) || el.getAttribute('aria-label') === locator.label;
            return norm(el.innerText || el.textContent) === norm(locator.text) &&
                !Array.from(el.children).some(c => norm(c.innerText || c.textContent) === norm(locator.text));
        });
    }
    nodes = nodes.filter(visible);
    if (nodes.length !== 1) throw new Error(nodes.length ? 'AMBIGUOUS: alvo ambíguo, múltiplos elementos visíveis.' : 'NOT_FOUND: alvo não encontrado ou invisível.');
    return nodes[0];
})""".replace('SCOPE(locator)',SCOPE+'(locator)')

ACTIONABLE = r"""function(editable) {
    if (this.nodeType!==1) throw new Error('UNVERIFIED: a referência não é um elemento acionável.');
    if (!this.isConnected) throw new Error('Alvo removido da página.');
    if (this.matches(':disabled') || this.getAttribute('aria-disabled') === 'true')
        throw new Error('Alvo desabilitado.');
    if (editable && this.type==='password') throw new Error('PERMISSION: campo protegido; use entrada humana no navegador.');
    if (editable && (!['INPUT','TEXTAREA'].includes(this.tagName) || this.readOnly ||
        ['file','hidden','checkbox','radio','button','submit','reset','range','color'].includes(this.type)))
        throw new Error('Campo não aceita digitação de texto.');
    this.scrollIntoView({block:'center', inline:'center', behavior:'instant'});
    const r = this.getBoundingClientRect(), s = getComputedStyle(this);
    const x = (Math.max(0,r.left) + Math.min(innerWidth,r.right))/2;
    const y = (Math.max(0,r.top) + Math.min(innerHeight,r.bottom))/2;
    let root=this.getRootNode();
    while (root.host) {
        if (root.mode!=='open') throw new Error('UNVERIFIED: Shadow DOM fechado.');
        root=root.host.getRootNode();
    }
    let hit=this.ownerDocument.elementFromPoint(x,y);
    while (hit && hit.shadowRoot) {
        const inner=hit.shadowRoot.elementFromPoint(x,y);
        if (!inner || inner===hit) break;
        hit=inner;
    }
    if (r.width <= 0 || r.height <= 0 || s.visibility !== 'visible' || s.display === 'none' ||
        !hit || !(hit === this || this.contains(hit))) throw new Error('Alvo oculto, coberto ou fora da tela.');
    let globalX=x, globalY=y, win=this.ownerDocument.defaultView;
    while (win!==win.top) {
        const frame=win.frameElement;
        if (!frame) throw new Error('UNVERIFIED: iframe de outra origem exige transporte próprio.');
        const bounds=frame.getBoundingClientRect();
        globalX+=bounds.left+frame.clientLeft; globalY+=bounds.top+frame.clientTop;
        const parent=frame.ownerDocument;
        const over=parent.elementFromPoint(globalX,globalY);
        if (over!==frame) throw new Error('UNVERIFIED: iframe coberto ou fora da tela.');
        win=parent.defaultView;
    }
    return {x:globalX,y:globalY,width:r.width,height:r.height};
}"""

FOCUS = r"""function() {
    this.focus();
    let active=this.ownerDocument.activeElement;
    while (active && active.shadowRoot && active.shadowRoot.activeElement) active=active.shadowRoot.activeElement;
    return active===this;
}"""
