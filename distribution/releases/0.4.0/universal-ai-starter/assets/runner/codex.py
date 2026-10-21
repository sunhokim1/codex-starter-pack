"""One observable CLI invocation per call. Failed calls retain observable usage."""
import json
import os
import signal
import subprocess
import time

from rev import contracts as c
from .runtime_safety import redact

TOKEN_KEYS = ('input_tokens', 'cached_input_tokens', 'output_tokens')


def aggregate(attempts):
    """Known subtotal is distinct from total; unknown never becomes zero."""
    result = {}
    for key in (*TOKEN_KEYS, 'elapsed_seconds', 'cli_invocations', 'backend_requests'):
        values = [a[key] for a in attempts]
        known = [x for x in values if x is not None]
        result[key] = dict(total=sum(known) if len(known) == len(values) else None,
                           known_subtotal=sum(known) if known else None,
                           unknown_attempts=len(values) - len(known))
    result.update(app_chat_usage=None, app_chat_model_changed=False,
                  backend_requests_note='unknown unless backend confirms; CLI invocations are observable')
    return result


def attempt(phase, model):
    return dict(phase=phase, status='interrupted', requested_model=model, actual_model=None,
                elapsed_seconds=None, input_tokens=None, cached_input_tokens=None, output_tokens=None,
                cli_invocations=0, backend_requests=None)


def parse_output(raw):
    messages, usages, errors = [], [], []
    completed = 0
    for line in raw.splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError()
        except (ValueError, TypeError):
            errors.append('invalid CLI JSON event')
            continue  # Retain later usage, including after an error event.
        kind = event.get('type')
        if kind in ('turn.completed', 'turn.failed'):
            usages.append(event.get('usage'))
        if kind in ('turn.failed', 'error'):
            errors.append('CLI reported failure')
        if kind == 'turn.completed':
            completed += 1
        item = event.get('item', {})
        if isinstance(item, dict) and kind == 'item.completed' and item.get('type') == 'agent_message':
            messages.append(item.get('text'))
    usage = {}
    for key in TOKEN_KEYS:
        values = [u.get(key) if isinstance(u, dict) else None for u in usages]
        valid = lambda x: type(x) is int and x >= 0
        usage[key] = sum(values) if values and all(valid(x) for x in values) else None
    if (usage['input_tokens'] is not None and usage['cached_input_tokens'] is not None
            and usage['cached_input_tokens'] > usage['input_tokens']):
        usage['cached_input_tokens'] = None
        errors.append('invalid cached usage')
    if completed != 1 or not messages or not isinstance(messages[-1], str):
        errors.append('missing/ambiguous completed CLI response')
    return dict(response=messages[-1] if messages else None, usage=usage, errors=errors)


def invoke(executable, model, project, prompt, timeout, schema, write, phase):
    record = attempt(phase, model)
    started = time.monotonic()
    args = [executable, 'exec', '--ephemeral', '--json', '--skip-git-repo-check',
            '--sandbox', 'workspace-write' if write else 'read-only', '--model', model,
            '--cd', str(project), '--output-schema', str(schema), '-']
    raw, stderr, code = '', '', None
    failure_kind = 'code'
    try:
        # Popen lets a startup failure remain zero observed invocations.
        options = dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else dict(start_new_session=True)
        with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8', errors='replace', shell=False, **options) as process:
            record['cli_invocations'] = 1
            try:
                raw, stderr = process.communicate(prompt, timeout=timeout)
                code = process.returncode
            except subprocess.TimeoutExpired:
                failure_kind = 'transient'
                stop_tree(process)
                raw, stderr = process.communicate()
                record['error'] = 'CLI deadline expired; inspect partial edits and explicitly reconcile before resume'
            except KeyboardInterrupt:
                failure_kind = 'transient'
                stop_tree(process)
                raw, stderr = process.communicate()
                record['error'] = 'CLI interrupted; inspect partial edits and explicitly reconcile before resume'
    except OSError:
        failure_kind = 'environment'
        record['error'] = 'CLI could not start; check executable and environment'
    finally:
        parsed = parse_output(raw)
        record.update(parsed['usage'], elapsed_seconds=time.monotonic() - started)
        record['status'] = 'succeeded' if code == 0 and not parsed['errors'] and 'error' not in record else 'failed'
        c.validate_usage(record_usage(record))
    # CLI currently provides no authoritative actual backend model/request identity.
    # Requested --model, thread IDs and local model settings are not confirmation.
    return redact(dict(usage=record_usage(record), response=parsed['response'],
                       error=record.get('error') or ('; '.join(parsed['errors']) if parsed['errors'] else
                                                     'CLI exited nonzero' if code else None),
                       failure_kind=failure_kind if record['status'] != 'succeeded' else None,
                       exit_code=code, stdout=raw, stderr=stderr))


def record_usage(record):
    return {k: record[k] for k in attempt('implementation', 'placeholder')}


def stop_tree(process):
    """Only the CLI process tree created by this call; no shared service shutdown."""
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=10, shell=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired):
            # Backend activity stays unknown; terminate at least the created parent.
            pass
        finally:
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
