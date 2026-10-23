"""Small DOM locator vocabulary. No claim of full accessibility-tree semantics.

Only the selected document is searched; frames and closed shadow roots require
another explicit route. Values are JSON data, never interpolated JavaScript.
"""

MAX_LOCATOR_CHARS = 500


def clean_locator(value):
    if isinstance(value, str):
        value = {"css": value.strip()}
    if not isinstance(value, dict) or set(value) - {"css", "role", "name", "label", "text"}:
        raise ValueError("Informe seletor CSS ou localizador por role/name, label ou text.")
    keys = set(value) & {"css", "role", "label", "text"}
    if len(keys) != 1 or ("name" in value and "role" not in value):
        raise ValueError("Use exatamente um tipo de localizador.")
    if any(not isinstance(v, str) or not v.strip() or len(v) > MAX_LOCATOR_CHARS for v in value.values()):
        raise ValueError("Localizador vazio ou longo demais.")
    return {k: v.strip() for k, v in value.items()}


RESOLVE = r"""(locator => {
    const norm = s => (s || '').replace(/\s+/g, ' ').trim();
    const visible = el => {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility === 'visible' && s.display !== 'none';
    };
    const label = el => Array.from(el.labels || []).map(l => norm(l.textContent)).join(' ');
    const name = el => norm(el.getAttribute('aria-label')) ||
        norm((el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id =>
            document.getElementById(id)?.textContent || '').join(' ')) ||
        label(el) || norm(el.innerText || el.getAttribute('alt') ||
            (['submit', 'button'].includes(el.type) ? el.value : ''));
    const role = el => el.getAttribute('role') || ({BUTTON:'button', A:el.href?'link':'',
        TEXTAREA:'textbox', SELECT:'combobox', IMG:'img'}[el.tagName]) ||
        (el.tagName === 'INPUT' ? ({checkbox:'checkbox', radio:'radio',
            button:'button', submit:'button', range:'slider', number:'spinbutton'}[el.type] || 'textbox') : '');
    let nodes;
    if (locator.css) nodes = Array.from(document.querySelectorAll(locator.css));
    else {
        nodes = Array.from(document.querySelectorAll('*')).filter(el => {
            if (locator.role) return role(el) === locator.role && (!locator.name || name(el) === norm(locator.name));
            if (locator.label) return label(el) === norm(locator.label) || el.getAttribute('aria-label') === locator.label;
            return norm(el.innerText || el.textContent) === norm(locator.text) &&
                !Array.from(el.children).some(c => norm(c.innerText || c.textContent) === norm(locator.text));
        });
    }
    nodes = nodes.filter(visible);
    if (nodes.length !== 1) throw new Error(nodes.length ? 'Alvo ambíguo: múltiplos elementos visíveis.' : 'Alvo não encontrado ou invisível.');
    return nodes[0];
})"""

ACTIONABLE = r"""function(editable) {
    if (!this.isConnected) throw new Error('Alvo removido da página.');
    if (this.matches(':disabled') || this.getAttribute('aria-disabled') === 'true')
        throw new Error('Alvo desabilitado.');
    if (editable && (!['INPUT','TEXTAREA'].includes(this.tagName) || this.readOnly ||
        ['file','hidden','checkbox','radio','button','submit','reset','range','color'].includes(this.type)))
        throw new Error('Campo não aceita digitação de texto.');
    this.scrollIntoView({block:'center', inline:'center', behavior:'instant'});
    const r = this.getBoundingClientRect(), s = getComputedStyle(this);
    const x = (Math.max(0,r.left) + Math.min(innerWidth,r.right))/2;
    const y = (Math.max(0,r.top) + Math.min(innerHeight,r.bottom))/2;
    const hit = document.elementFromPoint(x,y);
    if (r.width <= 0 || r.height <= 0 || s.visibility !== 'visible' || s.display === 'none' ||
        !hit || !(hit === this || this.contains(hit))) throw new Error('Alvo oculto, coberto ou fora da tela.');
    return {x,y,width:r.width,height:r.height};
}"""
