"""Authenticated loopback HTTP gateway, bounded model worker and persistent lifecycle.

State contains public connection metadata only; bearer credentials remain in an
inherited environment variable. No ACL, startup entry or shared runtime changes.
"""
if not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "rev"

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time

from . import contracts as c
from .errors import RevError, fail
from .loader import BUNDLE, check_rows, load_verified, regular
from .selector import Client, strict_json, token_value, validate_ready
from .hardware import normalize_mode, cpu_options, cpu_environment, configure_worker_cpu, preparation_threads


def safe_destination(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            fail('identity', 'Linked/reparse lifecycle paths are not allowed')
    return path


def write_exclusive(path, value):
    path = safe_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(c.json_bytes(value)); stream.flush(); os.fsync(stream.fileno())


def venv_interpreter(path):
    """Allow POSIX venv's final python symlink, never linked state/artifacts."""
    path = Path(os.path.abspath(path))
    safe_destination(path.parent)
    if path.parent.name != ('Scripts' if os.name == 'nt' else 'bin') or not path.is_file():
        fail('environment', 'Provide the explicit isolated venv bin/python or Scripts/python.exe')
    regular(path.parent.parent / 'pyvenv.cfg')
    return path


def connection_for(endpoint, runtime_id, token_env):
    lock_sha = __import__('hashlib').sha256((BUNDLE / 'contracts/upstream.lock.json').read_bytes()).hexdigest()
    return dict(contract_version=1, runtime_version='0.4.0', runtime_id=runtime_id,
                endpoint=endpoint, token_env=token_env, lock_sha256=lock_sha)


def authenticate(peer, headers, token, connection):
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = False
    origin = headers.get('Origin')
    duplicate = hasattr(headers, 'get_all') and any(len(headers.get_all(key, [])) != 1
        for key in ('Authorization', 'X-Rev-Runtime', 'X-Rev-Lock'))
    if (not local or duplicate or origin is not None or headers.get('Transfer-Encoding') is not None
            or not hmac.compare_digest(headers.get('Authorization', '').encode(), ('Bearer ' + token).encode())
            or headers.get('X-Rev-Runtime') != connection['runtime_id']
            or headers.get('X-Rev-Lock') != connection['lock_sha256']):
        fail('authentication', 'Local token/runtime identity required; browser origins and remote access are rejected')


def _model_worker(pipe, arguments):
    # A killed gateway must not leave its multi-GB worker orphaned (also on Windows).
    parent = mp.parent_process()
    def watch():
        while parent is not None and parent.is_alive():
            time.sleep(0.5)
        os._exit(1)
    threading.Thread(target=watch, daemon=True).start()
    torch_api = None
    restore_threads = None
    saved_environment = {key: os.environ.get(key) for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS')}
    try:
        arguments = dict(arguments)
        requested_threads = arguments.pop('cpu_threads', None)
        preparation = preparation_threads(requested_threads)
        allocation = configure_worker_cpu(preparation,
            arguments.pop('cpu_priority', 'normal'), arguments.pop('cpu_owned_job', False))
        allocation['requested_threads'] = requested_threads
        allocation['preparation_threads'] = preparation
        scorer = load_verified(**arguments)
        import torch  # already authenticated/imported by load_verified
        torch_api = torch
        restore_threads = torch.get_num_threads()
        allocation['preparation_torch_num_threads'] = restore_threads
        if preparation is not None and restore_threads != preparation:
            fail('resource', 'Actual preparation torch threads differ from stable CPU policy')
        if requested_threads is not None:
            torch.set_num_threads(requested_threads)
        allocation['torch_num_threads'] = torch.get_num_threads()
        if allocation['requested_threads'] is not None and allocation['torch_num_threads'] != allocation['requested_threads']:
            fail('resource', 'Actual torch threads differ from requested CPU allocation')
        scorer.info['cpu_allocation'] = allocation
        pipe.send(('ready', scorer.info))
        while True:
            operation, body = pipe.recv()
            if operation == 'stop':
                return
            rows = check_rows(scorer, body)
            begin = time.monotonic()
            response = scorer.score(body)
            c.validate_response(body, response)
            pipe.send(('result', dict(response=response, measurement=dict(encoded_tokens=[len(row[0]) for row in rows],
                request_bytes=len(c.json_bytes(body)), score_seconds=time.monotonic()-begin, evidence='actual-pinned-worker'))))
    except RevError as error:
        print(json.dumps(dict(worker_failure=error.kind, action=error.action)), file=sys.stderr, flush=True)
        pipe.send(('error', dict(kind=error.kind, action=error.action)))
    except BaseException as error:
        # Do not leak inputs, tokenizer errors, checkpoint metadata or credentials.
        # Stack locations and exception type identify the failing API without
        # reflecting its message (which may contain user context or credentials).
        import traceback
        traceback.print_tb(error.__traceback__)
        print('Worker exception type: ' + type(error).__name__, file=sys.stderr, flush=True)
        try:
            pipe.send(('error', dict(kind='model', action='Model worker failed; inspect pinned dependencies/resources, then explicitly restart; no fallback')))
        except (OSError, EOFError):
            pass
    finally:
        try:
            if torch_api is not None and restore_threads is not None:
                torch_api.set_num_threads(restore_threads)
        finally:
            for key, value in saved_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            pipe.close()


class Worker:
    def __init__(self, arguments, load_timeout=600, score_timeout=30):
        cpu_options(arguments.get('cpu_threads'), arguments.get('cpu_priority', 'normal'))
        if not 0 < load_timeout <= 1800 or not 0 < score_timeout <= 900:
            fail('configuration', 'Worker deadlines are outside bounded limits')
        context = mp.get_context('spawn')
        self.pipe, child = context.Pipe()
        self.process = context.Process(target=_model_worker, args=(child, arguments), daemon=True)
        self.score_timeout, self.ready = score_timeout, False
        saved_environment = {key: os.environ.get(key) for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS')}
        try:
            os.environ.update(cpu_environment(preparation_threads(arguments.get('cpu_threads')),
                                              arguments.get('cpu_priority', 'normal')))
            self.process.start()
        finally:
            child.close()
            for key, value in saved_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        try:
            self.info = self.receive(load_timeout, 'ready')
            self.info['deadlines'] = dict(load_seconds=load_timeout, score_seconds=score_timeout)
            self.ready = True
        except BaseException:
            self.close(); raise

    def receive(self, timeout, expected):
        if not self.pipe.poll(timeout):
            self.close()
            fail('timeout', 'Model worker deadline expired and worker was stopped; inspect resources and explicitly restart')
        try:
            kind, value = self.pipe.recv()
        except (EOFError, OSError):
            self.close(); fail('model', 'Worker exited; inspect local resources/dependencies and explicitly restart')
        if kind == 'error':
            self.close(); fail(value['kind'], value['action'])
        if kind != expected:
            self.close(); fail('protocol', 'Unexpected worker message; restart after inspection')
        return value

    def is_ready(self):
        if not self.process.is_alive():
            self.ready = False
        return self.ready

    def score(self, body):
        if not self.is_ready():
            fail('readiness', 'Worker is not ready; explicitly restart after inspection')
        try:
            self.pipe.send(('score', body))
        except (OSError, EOFError):
            self.close()
            fail('model', 'Worker pipe failed; inspect local resources and explicitly restart; no fallback')
        value = self.receive(self.score_timeout, 'result')
        self.info['last_score'] = value['measurement']
        return value['response']

    def close(self):
        self.ready = False
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.kill(); self.process.join(timeout=5)
        self.pipe.close()


def make_server(worker, token, runtime_id, token_env, host='127.0.0.1', port=0):
    if host != '127.0.0.1':
        fail('authentication', 'Service binds only 127.0.0.1; no remote/public bind option')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def handle(self):
            def expire():
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            timer = threading.Timer(getattr(worker, 'score_timeout', 30) + 12, expire)
            timer.daemon = True; timer.start()
            try:
                super().handle()
            finally:
                timer.cancel()

        def log_message(self, *args):
            pass  # Never log headers/context into stdout or public server logs.

        def reply(self, status, body):
            raw = c.json_bytes(body)
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try:
                self.wfile.write(raw)
            except OSError:
                pass

        def do_GET(self):
            # Even health requires authentication. It is not readiness evidence.
            try:
                authenticate(self.client_address[0], self.headers, token, self.server.connection_info)
                if self.path != '/health':
                    return self.reply(404, {'error': 'operation'})
                self.reply(200, {'ok': True})
            except RevError:
                self.reply(403, {'error': 'authentication'})

        def do_POST(self):
            try:
                authenticate(self.client_address[0], self.headers, token, self.server.connection_info)
                if self.path not in ('/ping', '/score', '/stop'):
                    return self.reply(404, {'error': 'operation'})
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= c.MAX_REQUEST_BYTES:
                    fail('oversize', 'Bounded Content-Length required')
                if self.headers.get('Content-Type') != 'application/json':
                    fail('input', 'JSON required')
                remaining, chunks = int(lengths[0]), []
                deadline = time.monotonic() + 10
                while remaining:
                    seconds = deadline - time.monotonic()
                    if seconds <= 0:
                        fail('timeout', 'Request body deadline expired')
                    self.connection.settimeout(seconds)
                    block = self.rfile.read1(min(remaining, 8192))
                    if not block:
                        fail('input', 'Incomplete request')
                    chunks.append(block); remaining -= len(block)
                body = strict_json(b''.join(chunks))
                if self.path == '/stop':
                    if body != {}:
                        fail('input', 'Stop takes no payload')
                    self.server.stopping = True
                    return self.reply(200, {'stopped': True, 'runtime_id': runtime_id, 'pid': os.getpid()})
                if self.path == '/ping':
                    if body != {}:
                        fail('input', 'Ping takes no payload')
                    info = dict(worker.info, runtime_id=runtime_id, pid=os.getpid(), runtime_version='0.4.0',
                                lock_sha256=self.server.connection_info['lock_sha256'], ready=worker.is_ready())
                    if info['ready']:
                        validate_ready(info, self.server.connection_info)
                    return self.reply(200, info)
                c.validate_request(body)
                self.reply(200, worker.score(body))
            except RevError as error:
                self.reply({'authentication': 403, 'oversize': 413, 'timeout': 504, 'readiness': 503}.get(error.kind, 400), {'error': error.kind})
            except (ValueError, TypeError, KeyError, OSError, c.ContractError):
                self.reply(400, {'error': 'invalid_request_or_worker_failure'})

    class Server(HTTPServer):
        request_queue_size = 4
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(10)
            return connection, address
    server = Server((host, port), Handler)
    server.timeout, server.stopping = 0.5, False
    server.connection_info = connection_for('http://127.0.0.1:%d' % server.server_port, runtime_id, token_env)
    return server


def serve(state, token_env, runtime_id, base, adapter, environment, device=0, dtype='bf16',
          load_timeout=600, score_timeout=30, cpu_threads=None, cpu_priority='normal', cpu_owned_job=False, **memory_options):
    device, dtype = normalize_mode(device, dtype)
    cpu_options(cpu_threads, cpu_priority)
    if cpu_priority == 'above-normal' and not cpu_owned_job:
        fail('configuration', 'AboveNormal requires the private owned smoke launch gate')
    state = safe_destination(state)
    if state.exists():
        fail('identity', 'Existing service state must be inspected/reconciled, never overwritten')
    token = token_value(token_env)
    worker = Worker(dict(base_directory=base, adapter_directory=adapter, environment=environment,
                         device=device, dtype=dtype, cpu_threads=cpu_threads, cpu_priority=cpu_priority,
                         cpu_owned_job=cpu_owned_job, **memory_options), load_timeout, score_timeout)
    try:
        with make_server(worker, token, runtime_id, token_env) as server:
            info = dict(worker.info, runtime_id=runtime_id, pid=os.getpid(), runtime_version='0.4.0',
                        lock_sha256=server.connection_info['lock_sha256'])
            validate_ready(info, server.connection_info)
            write_exclusive(state, dict(connection=server.connection_info, pid=os.getpid()))
            try:
                while not server.stopping:
                    server.handle_request()
            finally:
                try:
                    current = strict_json(regular(state).read_bytes())
                    if current.get('connection') == server.connection_info and current.get('pid') == os.getpid():
                        state.unlink()
                except (OSError, ValueError, RevError):
                    pass
    finally:
        worker.close()


def read_state(state):
    path = regular(safe_destination(state))
    if path.stat().st_size > 8192:
        fail('identity', 'Oversized lifecycle state; preserve and explicitly reconcile')
    value = strict_json(path.read_bytes())
    if not isinstance(value, dict) or set(value) != {'connection', 'pid'} or type(value['pid']) is not int:
        fail('identity', 'Incompatible state; preserve it and explicitly reconcile/archive; do not reuse SEV state')
    c.validate_connection(value['connection'])
    expected = connection_for(value['connection']['endpoint'], value['connection']['runtime_id'], value['connection']['token_env'])
    if expected != value['connection']:
        fail('identity', 'Runtime lock/state changed; inspect and explicitly reconcile')
    return value


def status(state, timeout=2):
    value = read_state(state)
    info = Client(value['connection'], timeout=timeout).ready()
    if info['pid'] != value['pid']:
        fail('identity', 'Process identity changed; no PID-only reuse or termination is permitted')
    return info


def stop(state):
    value = read_state(state)
    identity = Client(value['connection'], timeout=2).call('/ping')
    if any(identity.get(k) != v for k, v in dict(pid=value['pid'], runtime_id=value['connection']['runtime_id'],
            runtime_version='0.4.0', lock_sha256=value['connection']['lock_sha256']).items()):
        fail('identity', 'Stop target identity mismatch; do not terminate a state-file PID')
    reply = Client(value['connection'], timeout=10).call('/stop')
    if reply != dict(stopped=True, runtime_id=value['connection']['runtime_id'], pid=value['pid']):
        fail('identity', 'Stop acknowledgement mismatch; inspect service without killing a state-file PID')
    return reply


def ensure_started(state, python, base, adapter, environment, token_env='REV_AUTH_TOKEN', device=0, timeout=660, dtype='bf16',
                   load_timeout=600, score_timeout=30, cpu_threads=None, cpu_priority='normal', **memory_options):
    device, dtype = normalize_mode(device, dtype)
    cpu_options(cpu_threads, cpu_priority)
    if cpu_priority != 'normal':
        fail('configuration', 'AboveNormal is available only in the private owned smoke job')
    def reuse():
        info = status(state)
        allocation = info.get('cpu_allocation', {})
        if ((cpu_threads is not None and allocation.get('requested_threads') != cpu_threads)
                or allocation.get('requested_priority', 'normal') != cpu_priority):
            fail('configuration', 'Existing CPU allocation differs; explicitly stop/restart')
        if (info['device'], info['dtype']) != (device, dtype):
            fail('configuration', 'Existing service uses a different device/dtype; explicitly stop/restart it rather than silently changing modes')
        plan = info.get('memory_plan', {})
        if memory_options.get('memory_mode', 'full-resident') != plan.get('mode', 'full-resident'):
            fail('configuration', 'Existing service memory mode differs; explicitly stop/restart, never silently replace')
        if plan and any(value is not None and plan.get(key) != value for key, value in memory_options.items()
                        if key in ('row_token_budget', 'process_budget_bytes', 'safety_margin_bytes')):
            fail('configuration', 'Existing service memory budget differs; explicitly stop/restart')
        return info
    state = safe_destination(state)
    if state.exists():
        return reuse()  # Never replace stale/incompatible state or replay a previous startup.
    if not 0 < timeout <= 1860 or timeout <= load_timeout or not 0 < load_timeout <= 1800 or not 0 < score_timeout <= 900:
        fail('configuration', 'Startup must exceed load deadline and be at most 1860s; load <=1800s, score <=900s')
    token_value(token_env)
    from .hardware import diagnose, require_hardware
    if memory_options.get('memory_mode', 'full-resident') == 'full-resident':
        require_hardware(diagnose(), device, dtype)
    lock = state.with_suffix(state.suffix + '.start-lock')
    write_exclusive(lock, {'pid': os.getpid(), 'action': 'Inspect service before explicitly removing a stale lock'})
    process = None
    try:
        if state.exists():
            return reuse()
        runtime_id = secrets.token_hex(24)
        command = [str(venv_interpreter(python)), '-I', '-S', '-B', str(Path(__file__).resolve()), 'serve', '--state', str(state),
                   '--base', str(base), '--adapter', str(adapter), '--environment', str(environment),
                   '--token-env', token_env, '--runtime-id', runtime_id, '--device', device, '--dtype', dtype]
        command += ['--load-timeout', str(load_timeout), '--score-timeout', str(score_timeout)]
        command += ['--cpu-priority', cpu_priority]
        if cpu_threads is not None:
            command += ['--cpu-threads', str(cpu_threads)]
        for key, value in memory_options.items():
            if value is not None:
                command += ['--' + key.replace('_', '-'), str(value)]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if state.exists():
                value = read_state(state)
                if value['pid'] != process.pid or value['connection']['runtime_id'] != runtime_id:
                    fail('identity', 'Startup state does not belong to the process just launched')
                return status(state)
            if process.poll() is not None:
                fail('startup', 'Service failed before readiness; run foreground serve to see sanitized failure; inspect environment/snapshots before retry')
            time.sleep(0.1)
        fail('timeout', 'Startup deadline expired; inspect resources/state before explicitly retrying')
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        raise
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Rev 격리 로컬 서비스: 기존 SEV 또는 프로젝트 상태를 변경하지 않는다')
    parser.add_argument('operation', choices=['start', 'serve', 'status', 'stop'])
    parser.add_argument('--state', required=True)
    parser.add_argument('--base'); parser.add_argument('--adapter'); parser.add_argument('--environment')
    parser.add_argument('--token-env', default='REV_AUTH_TOKEN'); parser.add_argument('--runtime-id')
    parser.add_argument('--python', default=sys.executable); parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--dtype', choices=['bf16', 'fp16', 'fp32'], default='bf16')
    parser.add_argument('--cpu-threads', type=int)
    parser.add_argument('--cpu-priority', choices=['normal', 'above-normal'], default='normal')
    parser.add_argument('--load-timeout', type=float, default=600)
    parser.add_argument('--score-timeout', type=float, default=30)
    parser.add_argument('--startup-timeout', type=float, default=660)
    parser.add_argument('--memory-mode', choices=['full-resident', 'bounded-cpu'], default='full-resident')
    parser.add_argument('--offload-directory')
    parser.add_argument('--row-token-budget', type=int, default=16384)
    parser.add_argument('--process-budget-bytes', type=int)
    parser.add_argument('--safety-margin-bytes', type=int)
    parser.add_argument('--owned-launch-gate', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--preflight-request', help='Private smoke request checked with the official encoder before model loading')
    args = parser.parse_args()
    memory_options = {key: getattr(args, key) for key in ('memory_mode', 'offload_directory', 'row_token_budget',
                       'process_budget_bytes', 'safety_margin_bytes')}
    try:
        cpu_options(args.cpu_threads, args.cpu_priority)
        if args.preflight_request:
            path = regular(args.preflight_request)
            if path.stat().st_size > c.MAX_REQUEST_BYTES:
                fail('oversize', 'Preflight request exceeds transport bound')
            request = strict_json(path.read_bytes())
            c.validate_request(request)
            memory_options['preflight_request'] = request if args.operation == 'serve' else str(path)
        if args.operation in ('start', 'serve') and not all((args.base, args.adapter, args.environment)):
            fail('configuration', 'Explicit local base/adapter/environment resources are required')
        if args.operation == 'serve':
            if not args.runtime_id:
                fail('configuration', 'Explicit unique runtime-id is required for foreground serve')
            if args.owned_launch_gate and sys.stdin.buffer.read(1) != b'1':
                fail('identity', 'Owned supervisor launch gate not released')
            serve(args.state, args.token_env, args.runtime_id, args.base, args.adapter, args.environment, args.device, args.dtype,
                  args.load_timeout, args.score_timeout, cpu_threads=args.cpu_threads, cpu_priority=args.cpu_priority,
                  cpu_owned_job=args.owned_launch_gate, **memory_options)
            result = {'status': 'stopped'}
        elif args.operation == 'start':
            result = ensure_started(args.state, args.python, args.base, args.adapter, args.environment, args.token_env, args.device, dtype=args.dtype, timeout=args.startup_timeout,
                                    load_timeout=args.load_timeout, score_timeout=args.score_timeout,
                                    cpu_threads=args.cpu_threads, cpu_priority=args.cpu_priority, **memory_options)
        else:
            result = (status if args.operation == 'status' else stop)(args.state)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (RevError, c.ContractError, OSError, ValueError) as error:
        # Actions from our typed failures are static; arbitrary exception text may contain secrets.
        print(json.dumps({'status': 'failed', 'kind': getattr(error, 'kind', 'configuration'),
                          'action': error.action if isinstance(error, RevError) else 'Inspect isolated runtime paths/configuration; preserve old state; no fallback'}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
