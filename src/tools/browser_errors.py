"""Typed browser failures; observations never imply permission to act."""


class BrowserError(RuntimeError):
    def __init__(self, message, code='UNVERIFIED', suggestions=None):
        super().__init__(message)
        self.code = code
        self.suggestions = suggestions or ['Inspecione a página novamente e use um alvo único da sessão atual.']
