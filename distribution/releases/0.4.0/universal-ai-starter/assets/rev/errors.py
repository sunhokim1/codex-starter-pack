"""Actionable failures; no inference failure can select a paid fallback."""


class RevError(RuntimeError):
    def __init__(self, kind, action):
        self.kind = kind
        self.action = action
        super().__init__(kind + ': ' + action)


def fail(kind, action):
    raise RevError(kind, action)
