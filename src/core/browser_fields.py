"""Bind explicit user-provided field values to uniquely observed labels.

Ambiguous or implicit values stay with the model. This never types by itself or
derives an instruction from a web page; registry permissions still govern typing.
"""
import re


def requested_fields(goal, controls):
    goal = str(goal).split('\n\n',1)[0]
    fields = [item for item in controls if item.get('role') in {'textbox','searchbox','spinbutton'}
              and item.get('name') and not item.get('protected')]
    names = [item['name'] for item in fields]
    bindings = []
    for field in fields:
        name = field['name']
        if names.count(name)!=1:
            continue
        match = re.search(r'\b'+re.escape(name)+r'\b[^.!?\n]{0,100}?\bcom\s+(.+)',goal,re.I)
        if not match:
            continue
        value = match[1].strip()
        if value[:1] in {'"',"'",'“'}:
            quote = '”' if value[0]=='“' else value[0]
            end = value.find(quote,1)
            if end<0:
                continue
            value = value[1:end]
        else:
            labels = '|'.join(re.escape(label) for label in names)
            value = re.split(r'\s+e\s+(?:o\s+campo\s+)?(?:'+labels+r')\b[^.!?\n]{0,60}\bcom\b|'
                             r',\s*(?:e\s+)?(?:salv\w*|env\w*|clic\w*|depois|em seguida)\b|[.;](?:\s|$)',
                             value,maxsplit=1,flags=re.I)[0].strip()
        if value and len(value)<=2000:
            bindings.append({'name':name,'ref':field['ref'],'text':value})
    if not bindings and len(fields)==1:
        match = re.search(r'\bpesquise\s+(.+?)\s+(?:no|pelo|usando o)\s+(?:formulário|campo|busca)\b',goal,re.I)
        if match:
            bindings.append({'name':fields[0]['name'],'ref':fields[0]['ref'],'text':match[1].strip(' "“”')})
    return bindings


def pending_fields(state):
    return [item for item in state.get('bindings',[]) if state.get('typed_fields',{}).get(item['name'])!=item['text']]
