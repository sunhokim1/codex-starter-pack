"""Loopback-only, authenticated persistent SEV. Never executes coding tasks."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

# Source layout shares the helper with runner; installed runtimes have it beside us.
if (Path(__file__).resolve().parents[1] / 'runner/runtime_safety.py').is_file():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runner'))
from runtime_safety import private_permissions, private_write, redact, reject_links

LIMIT = 1024 * 1024
TEXT_LIMIT = 32768


def read_message(stream):
    line = stream.readline(LIMIT + 1)
    if len(line) > LIMIT or not line.endswith(b'\n'):
        raise ValueError('invalid or oversized SEV message')
    try:
        message = json.loads(line)
    except (ValueError, UnicodeError):
        raise ValueError('invalid SEV JSON') from None
    if not isinstance(message, dict):
        raise ValueError('SEV message must be an object')
    return message


def validate_request(message, token):
    supplied = message.get('token')
    if not isinstance(supplied, str) or not secrets.compare_digest(supplied, token):
        raise ValueError('SEV authentication failed')
    op = message.get('op')
    allowed = {'token', 'op', 'request', 'facts'} if op == 'select' else {'token', 'op'}
    if op not in ('select', 'status', 'stop') or not set(message) <= allowed:
        raise ValueError('invalid SEV operation or fields')
    if op == 'select':
        if not isinstance(message.get('request'), str) or not isinstance(message.get('facts', ''), str):
            raise ValueError('SEV request and facts must be strings')
        if len(message['request']) + len(message.get('facts', '')) > TEXT_LIMIT:
            raise ValueError('SEV text exceeds capacity')
    return op


def request(state, message, timeout=90):
    info = json.loads(reject_links(state).read_text(encoding='utf-8'))
    if (not isinstance(info, dict) or not isinstance(info.get('token'), str) or
            type(info.get('port')) is not int or not 1 <= info['port'] <= 65535):
        raise ValueError('invalid SEV state')
    message = dict(message, token=info['token'])
    payload = json.dumps(message, ensure_ascii=True).encode() + b'\n'
    if len(payload) > LIMIT:
        raise ValueError('SEV request exceeds 1 MiB')
    with socket.create_connection(('127.0.0.1', info['port']), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(payload)
        result = read_message(connection.makefile('rb'))
    if not result.get('ok'):
        raise ValueError(result.get('error', 'SEV failed'))
    return result


def serve(state):
    from sev_keyword_selector import KeywordSelector
    from sev_long_candidate import LongCandidate
    from selector import HERE
    start = time.monotonic()
    model = LongCandidate()
    model.load(HERE / 'sev-long-candidate.npz')
    selector = KeywordSelector()
    selector.fallback = model
    load_seconds = time.monotonic() - start
    token = secrets.token_hex(32)
    state = reject_links(state)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        info = {'port': listener.getsockname()[1], 'token': token, 'pid': os.getpid()}
        private_write(state, json.dumps(info))
        count = 0
        try:
            stopping = False
            while not stopping:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(10)
                    try:
                        message = read_message(connection.makefile('rb'))
                        op = validate_request(message, token)
                        result = {'ok': True, 'pid': os.getpid(), 'requests': count,
                                  'model_load_seconds': load_seconds}
                        if op == 'select':
                            result['selection'] = redact(selector.select(redact(message['request']), redact(message.get('facts', ''))))
                            count += 1
                            result['requests'] = count
                        elif op == 'stop':
                            stopping = True
                        elif op != 'status':
                            raise ValueError('unknown SEV operation')
                    except Exception:
                        # Untrusted inputs and selector failures must not terminate the daemon
                        # or echo request contents into diagnostics.
                        result = {'ok': False, 'error': 'invalid SEV request or selector failure'}
                    try:
                        connection.sendall(json.dumps(result, ensure_ascii=True).encode() + b'\n')
                    except OSError:
                        pass
        finally:
            try:
                if state.exists() and json.loads(state.read_text())['token'] == token:
                    state.unlink()
            except (OSError, ValueError, KeyError, TypeError):
                pass


def ensure_started(state, python, script, timeout=90):
    state = reject_links(state)
    try:
        return request(state, {'op': 'status'}, timeout=2)
    except PermissionError:
        raise
    except (OSError, ValueError):
        pass
    state.parent.mkdir(parents=True, exist_ok=True)
    lock = state.with_suffix('.lock')
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError('SEV startup lock timed out; check service before removing lock')
            try:
                return request(state, {'op': 'status'}, timeout=2)
            except PermissionError:
                raise
            except (OSError, ValueError):
                time.sleep(.1)
    os.close(fd)
    try:
        try:
            return request(state, {'op': 'status'}, timeout=2)
        except PermissionError:
            raise
        except (OSError, ValueError):
            pass
        log_path = reject_links(state.with_suffix('.log'))
        if not log_path.exists():
            private_write(log_path, '')
        private_permissions(log_path)
        with log_path.open('ab') as log:
            child = subprocess.Popen([str(python), str(script), 'serve', '--state', str(state)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        while time.monotonic() < deadline:
            try:
                return request(state, {'op': 'status'}, timeout=2)
            except PermissionError:
                child.terminate()
                child.wait(timeout=10)
                raise
            except (OSError, ValueError):
                if child.poll() is not None:
                    raise ValueError('SEV startup failed; see local service log')
                time.sleep(.1)
        child.terminate()
        child.wait(timeout=10)
        raise ValueError('SEV startup timed out')
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('op', choices=['serve', 'start', 'status', 'stop', 'select'])
    parser.add_argument('--state', required=True)
    parser.add_argument('--task-file')
    parser.add_argument('--context-file')
    args = parser.parse_args()
    if args.op == 'serve':
        serve(args.state)
        return
    if args.op in ('start', 'select'):
        result = ensure_started(args.state, sys.executable, __file__)
    if args.op == 'select':
        result = request(args.state, {'op': 'select',
            'request': Path(args.task_file).read_text(encoding='utf-8-sig'),
            'facts': Path(args.context_file).read_text(encoding='utf-8-sig') if args.context_file else ''})
    elif args.op in ('status', 'stop'):
        result = request(args.state, {'op': args.op})
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
