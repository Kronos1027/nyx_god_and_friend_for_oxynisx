"""Canonical production browser contract, shared by UI/CLI and acceptance harness."""
from tools.registry import ToolSpec
from tools.browser_tool import is_sensitive_action, requires_external_confirmation


def browser_tool_spec():
    return ToolSpec(
        name="browser",
        description="Navegador real: open navega; read/tables/inspect observam; refs exigem snapshot; mídia e download explícitos",
        destructive=False,
        destructive_probe=requires_external_confirmation,
        sensitive=False,
        sensitive_probe=lambda p: is_sensitive_action(p.get("action")),
        input_contract={"action": "open|read|inspect|click|type|select|hover|press|wait|wait_text|status|media_status|media_play|media_pause|tabs|new_tab|switch_tab|close_tab|links|tables|download|screenshot|close",
            "path": "download: primeiro open e links, depois URL observada e caminho exato novo permitido, até50MiB; confirma sempre, não executa",
            "url": "http(s) somente open/new_tab/download; read não navega", "selector": "CSS, para click/type/wait; mídia opcional, só um elemento",
            "locator": "Prefira {ref, snapshot} do inspect. Fallback: {role,name}, {label}, {text}, {css}; escopos opcionais shadow/frame como listas de CSS (até8), só roots abertos/mesma origem",
            "ref": "e1, e2... do inspect, junto de snapshot; expira30s e invalida com documento/aba/identidade. Não invente ref",
            "snapshot": "Token do inspect para usar ref. Omitir selector e locator quando usar ref no nível superior",
            "value": "Valor exato da opção HTML SELECT simples, para select",
            "key": "Para press: Enter, Tab, Escape, setas, Home/End, PageUp/PageDown, Space ou Ctrl+A; envio não prova efeito",
            "submit": "Opcional booleano em type; true envia Enter depois de conferir o campo e exige confirmação de efeito externo",
            "text": "Texto de type/wait_text", "expected_text": "Pós-condição de click; sem ela, clique enviado não prova conclusão",
            "tab_id": "ID retornado por tabs, para switch_tab/close_tab",
            "login": "inspect mostra indícios de login; peça interação humana. Nunca solicite senha no chat.",
            "playback": "media_status deve confirmar tempo de mídia avançando antes de dizer que está tocando; ausência de estado é incerteza."},
    )
