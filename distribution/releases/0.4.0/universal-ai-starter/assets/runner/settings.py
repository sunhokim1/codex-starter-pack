"""Strict, dependency-free settings parsing; no selection backend here."""
import json
import re
from pathlib import Path

def config_from(path):
    """Dependency-free mapping/scalar YAML subset used by shipped settings.

    Reject unsupported YAML rather than silently ignore executable configuration.
    Command strings may be single/double quoted; use single-line shell commands.
    """
    if not Path(path).exists():
        return {}, 'unset'
    root = {}
    stack = [(-2, root)]
    for number, raw in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'( *)([A-Za-z_][A-Za-z_0-9-]*):(?: +(.*))?', raw)
        if not match or '\t' in raw or len(match[1]) % 2:
            raise ValueError(f'{path}:{number}: unsupported YAML; use mappings and single-line scalars')
        indent, key, value = len(match[1]), match[2], match[3]
        while stack[-1][0] >= indent:
            stack.pop()
        if indent != stack[-1][0] + 2:
            raise ValueError(f'{path}:{number}: invalid indentation')
        parent = stack[-1][1]
        if key in parent:
            raise ValueError(f'{path}:{number}: duplicate key {key}')
        if value is None or value.startswith('#'):
            parsed = {}
        elif value.startswith('"'):
            parsed = json.loads(value)
        elif value.startswith("'"):
            if not value.endswith("'"):
                raise ValueError('unterminated YAML string')
            parsed = value[1:-1].replace("''", "'")
        else:
            value = value.split(' #', 1)[0].rstrip()
            if value in ('null', '~'): parsed = None
            elif value in ('true', 'false'): parsed = value == 'true'
            elif re.fullmatch(r'0|[1-9][0-9]*', value): parsed = int(value)
            elif value.startswith('[') and value.endswith(']'):
                parsed = [v.strip() for v in value[1:-1].split(',') if v.strip()]
            elif value.startswith(('|', '>', '&', '*', '!', '{', '[')):
                raise ValueError('unsupported YAML scalar')
            else: parsed = value
        parent[key] = parsed
        if isinstance(parsed, dict): stack.append((indent, parsed))
    return root, 'configured'
