"""Small shared primitives for private files and bounded diagnostic output."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import uuid


def reject_links(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and
                getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('linked/reparse path is not allowed')
    return path


def private_permissions(path):
    if os.name == 'nt':
        options = dict(capture_output=True, text=True, check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        identity = subprocess.run(['whoami.exe', '/user', '/fo', 'csv', '/nh'], **options)
        sid = next(csv.reader(io.StringIO(identity.stdout)))[-1].strip()
        if not re.fullmatch(r'S-\d+(?:-\d+)+', sid):
            raise ValueError('could not identify current user SID')
        subprocess.run(['icacls.exe', str(path), '/inheritance:r', '/grant:r', f'*{sid}:F'], **options)
    else:
        os.chmod(path, 0o600)


def private_write(path, data):
    """Protect an exclusive temporary file before writing, then atomically replace."""
    path = reject_links(path)
    if path.exists() and not path.is_file():
        raise ValueError('private file destination is not a regular file')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.close(fd)
        private_permissions(temp)
        with temp.open('wb') as stream:
            stream.write(data.encode('utf-8') if isinstance(data, str) else data)
            stream.flush()
            os.fsync(stream.fileno())
        reject_links(path)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


_KEY = r'(?:api[_-]?key|password|passwd|secret|access[_-]?token|refresh[_-]?token|client[_-]?secret|token)'
_ASSIGN = re.compile(r'(?i)([\"\']?\b' + _KEY + r'[\"\']?\s*[:=]\s*)(?:"[^"\n]*"|\'[^\'\n]*\'|[^\s,;&}\]]+)')
_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', re.S),
    re.compile(r'\bsk-[A-Za-z0-9_-]{20,}'),
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(r'\bAKIA[A-Z0-9]{16}\b'),
    re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*'),
    re.compile(r'(?i)(?:https?|postgres(?:ql)?|mysql)://[^\s/@:]+:[^\s/@]+@'),
)


def redact(value):
    """Best-effort known credential filtering; arbitrary prose is not a secret detector."""
    if isinstance(value, str):
        for pattern in _PATTERNS:
            value = pattern.sub('[REDACTED]', value)
        return _ASSIGN.sub(lambda match: match[1] + '"[REDACTED]"', value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: '[REDACTED]' if re.fullmatch(_KEY, key, re.I) else redact(item)
                for key, item in value.items()}
    return value


def fingerprint(text):
    return {'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'characters': len(text)}


def summary(report):
    """Console/status output deliberately excludes goal, facts, prompts and raw checks."""
    keys = ('status', 'reason', 'error', 'runs', 'max_runs', 'elapsed_seconds',
            'max_seconds', 'app_chat_model_changed', 'verification_owner')
    return redact({key: report[key] for key in keys if key in report})
