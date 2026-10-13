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

LIMIT = 1024 * 1024


def read_message(stream):
    line = stream.readline(LIMIT + 1)
    if len(line) > LIMIT or not line.endswith(b'\n'):
        raise ValueError('invalid or oversized SEV message')
    return json.loads(line)


def request(state, message, timeout=90):
    info = json.loads(Path(state).read_text(encoding='utf-8'))
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
    state = Path(state)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        info = {'port': listener.getsockname()[1], 'token': token, 'pid': os.getpid()}
        temp = state.with_suffix('.tmp')
        temp.write_text(json.dumps(info), encoding='utf-8')
        temp.replace(state)
        count = 0
        try:
            stopping = False
            while not stopping:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(10)
                    try:
                        message = read_message(connection.makefile('rb'))
                        if not secrets.compare_digest(str(message.get('token', '')), token):
                            raise ValueError('SEV authentication failed')
                        op = message.get('op')
                        result = {'ok': True, 'pid': os.getpid(), 'requests': count,
                                  'model_load_seconds': load_seconds}
                        if op == 'select':
                            result['selection'] = selector.select(message['request'], message.get('facts', ''))
                            count += 1
                            result['requests'] = count
                        elif op == 'stop':
                            stopping = True
                        elif op != 'status':
                            raise ValueError('unknown SEV operation')
                    except (ValueError, KeyError, TypeError, OSError) as error:
                        result = {'ok': False, 'error': str(error)}
                    try:
                        connection.sendall(json.dumps(result, ensure_ascii=True).encode() + b'\n')
                    except OSError:
                        pass
        finally:
            if state.exists() and json.loads(state.read_text())['token'] == token:
                state.unlink()


def ensure_started(state, python, script, timeout=90):
    state = Path(state).resolve()
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
        with state.with_suffix('.log').open('ab') as log:
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
