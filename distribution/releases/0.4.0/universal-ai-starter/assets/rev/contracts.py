"""Versioned, fail-closed boundary contracts; no network, model import or state writes."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

STATE_VERSION = 4
MODELS = {"worker": "gpt-6-luna", "main": "gpt-6.1-sol"}
MAX_REQUEST_BYTES = 262144  # Local transport policy, NOT a tokenizer estimate.
MAX_ROW_TOKENS = 16384


class ContractError(ValueError):
    pass


class RequestTooLarge(ContractError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def obj(value, required, optional=()):
    require(isinstance(value, dict), "expected object")
    require(set(required) <= value.keys() <= set(required) | set(optional), "missing/unknown fields")
    return value


def text(value):
    require(isinstance(value, str) and bool(value.strip()), "expected nonempty string")
    return value


def number(value, nullable=False, integer=False):
    if value is None and nullable:
        return
    require(type(value) in ((int,) if integer else (int, float)), "expected number")
    require(math.isfinite(value) and value >= 0, "expected finite nonnegative number")


def digest(value, length=64):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value), "invalid digest/revision")


def json_bytes(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise ContractError("invalid JSON") from error


def validate_lock(lock):
    obj(lock, ('contract_version', 'source', 'adapter', 'base', 'dependencies', 'unresolved', 'reconciliation'))
    require(type(lock['contract_version']) is int and lock['contract_version'] == 1, "unsupported lock")
    for name in ('source', 'adapter', 'base'):
        item = obj(lock[name], ('repo', 'revision', 'artifacts', 'provenance'))
        text(item['repo']); digest(item['revision'], 40); text(item['provenance'])
        require(isinstance(item['artifacts'], dict) and item['artifacts'], "artifact hashes required")
        for filename, checksum in item['artifacts'].items():
            require(isinstance(filename, str) and not filename.startswith('/') and '\\' not in filename
                    and ':' not in filename and all(p not in ('', '.', '..') for p in filename.split('/')), "unsafe artifact path")
            digest(checksum)
    require(isinstance(lock['dependencies'], dict) and lock['dependencies'], "dependencies required")
    for name, dependency in lock['dependencies'].items():
        text(name); obj(dependency, ('version', 'provenance', 'status'))
        require(dependency['status'] in ('upstream_pinned', 'unresolved'), "invalid dependency status")
        text(dependency['provenance'])
        if dependency['status'] == 'upstream_pinned':
            text(dependency['version'])
        else:
            require(dependency['version'] is None, "unresolved version must be null")
    require(isinstance(lock['unresolved'], list), "unresolved list required")
    for item in lock['unresolved']:
        text(item)
    text(lock['reconciliation'])
    return lock


def verify_artifacts(directory, artifacts):
    """Call BEFORE import/exec/torch.load; returns verified paths, never loads them."""
    root = Path(directory).resolve(strict=True)
    require(isinstance(artifacts, dict) and artifacts, "artifact manifest required")
    verified = {}
    for name, expected in artifacts.items():
        digest(expected)
        require(isinstance(name, str) and not name.startswith('/') and ':' not in name and '\\' not in name
                and all(p not in ('', '.', '..') for p in name.split('/')), "unsafe artifact path")
        path = (root / name).resolve(strict=True)
        require(path.is_relative_to(root) and path.is_file(), "artifact escapes root")
        checksum = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                checksum.update(block)
        require(checksum.hexdigest() == expected, "artifact integrity mismatch: " + name)
        verified[name] = path
    return verified


def require_installable(lock):
    validate_lock(lock)
    require(not lock['unresolved'] and all(d['status'] == 'upstream_pinned' for d in lock['dependencies'].values()),
            "installation blocked: resolve dependency versions, wheel integrity and hardware support first")


def score_request(context, instructions, question_id='execution_model'):
    """All mandatory context is passed losslessly. No keyword routing/truncation."""
    obj(context, ('task', 'goal', 'facts', 'risks', 'constraints', 'uncertainty', 'dependencies'))
    body = {'state': copy.deepcopy(context), 'questions': [{
        'id': text(question_id), 'instructions': text(instructions), 'criteria': {
            'worker': 'Use gpt-6-luna for implementation with the full mandatory context and constraints.',
            'main': 'Use gpt-6.1-sol when implementation needs stronger reasoning with the same context and constraints.'}}]}
    validate_request(body)
    return body


def validate_request(body):
    obj(body, ('state', 'questions'))
    if len(json_bytes(body)) > MAX_REQUEST_BYTES:
        raise RequestTooLarge('request too large; narrow direct dependencies explicitly, never truncate mandatory context')
    require(isinstance(body['questions'], list) and body['questions'], "questions required")
    seen = set()
    for q in body['questions']:
        obj(q, ('id', 'instructions', 'criteria')); text(q['id']); text(q['instructions'])
        require(q['id'] not in seen, "duplicate question id"); seen.add(q['id'])
        require(isinstance(q['criteria'], dict) and len(q['criteria']) >= 2, "options required")
        for key, description in q['criteria'].items():
            text(key); text(description)
    return body


def validate_response(request, response):
    validate_request(request)
    obj(response, ('answers', 'server_seconds', 'path', 'rows', 'generated_tokens'))
    require(isinstance(response['answers'], dict), "answers object required")
    require(set(response['answers']) == {q['id'] for q in request['questions']}, "answer IDs mismatch")
    number(response['server_seconds'])
    require(response['path'] == 'rows' and type(response['generated_tokens']) is int and response['generated_tokens'] == 0, "unexpected server protocol")
    require(isinstance(response['rows'], list) and len(response['rows']) == len(request['questions']), "rows mismatch")
    for row in response['rows']:
        obj(row, ('gpu_seconds', 'batch_rows', 'batch_padded_tokens', 'queued_seconds'))
        for key, value in row.items():
            number(value, integer=key in ('batch_rows', 'batch_padded_tokens'))
    for q in request['questions']:
        answer = obj(response['answers'][q['id']], ('choice', 'probabilities'))
        p = answer['probabilities']
        require(isinstance(p, dict) and set(p) == set(q['criteria']), "probability options mismatch")
        for value in p.values():
            number(value); require(value <= 1, "probability outside [0,1]")
        require(abs(sum(p.values()) - 1) <= 1e-5, "probabilities must sum to one")
        require(isinstance(answer['choice'], str) and answer['choice'] in p
                and p[answer['choice']] == max(p.values()), "choice inconsistent with probabilities")
    return response


def validate_connection(connection):
    obj(connection, ('contract_version', 'runtime_version', 'runtime_id', 'endpoint', 'token_env', 'lock_sha256'))
    require(type(connection['contract_version']) is int and connection['contract_version'] == 1
            and connection['runtime_version'] == '0.4.0', "incompatible runtime")
    text(connection['runtime_id']); digest(connection['lock_sha256'])
    try:
        url = urlsplit(text(connection['endpoint']))
        port = url.port
    except ValueError as error:
        raise ContractError('invalid port') from error
    require(url.scheme == 'http' and url.hostname in ('127.0.0.1', '::1') and port is not None
            and 0 < port < 65536 and url.username is None and url.password is None
            and url.path in ('', '/') and not url.query and not url.fragment, "authenticated loopback endpoint required")
    require(isinstance(connection['token_env'], str) and re.fullmatch('[A-Z][A-Z0-9_]*', connection['token_env']), "token environment reference required")
    return connection


def validate_models(models):
    obj(models, ('planning_model', 'execution_model'))
    require(models['planning_model'] == MODELS['main'], "Sol planning required")
    require(models['execution_model'] is None or (isinstance(models['execution_model'], str)
            and models['execution_model'] in MODELS), "invalid global execution override")
    return models


def execution_override(models, task_override=None):
    validate_models(models)
    require(task_override is None or (isinstance(task_override, str) and task_override in MODELS), "invalid task execution override")
    # A non-null result bypasses Rev entirely. Planning never becomes an override.
    return task_override if task_override is not None else models['execution_model']


def validate_usage(attempt):
    obj(attempt, ('phase', 'status', 'requested_model', 'actual_model', 'elapsed_seconds', 'input_tokens',
                  'cached_input_tokens', 'output_tokens', 'cli_invocations', 'backend_requests'))
    require(attempt['phase'] in ('planning', 'implementation', 'retry', 'escalation', 'replan'), "invalid usage phase")
    require(attempt['status'] in ('succeeded', 'failed', 'interrupted'), "invalid attempt status")
    text(attempt['requested_model'])
    if attempt['actual_model'] is not None:
        text(attempt['actual_model'])
    for key in ('elapsed_seconds', 'input_tokens', 'cached_input_tokens', 'output_tokens', 'backend_requests'):
        number(attempt[key], nullable=True, integer=key != 'elapsed_seconds')
    number(attempt['cli_invocations'], integer=True)
    if attempt['input_tokens'] is not None and attempt['cached_input_tokens'] is not None:
        require(attempt['cached_input_tokens'] <= attempt['input_tokens'], "cached tokens exceed input")
    return attempt


def validate_evidence(check):
    obj(check, ('name', 'command', 'scope', 'status', 'producer', 'state_sha256', 'executed', 'exit_code', 'reason'))
    text(check['name']); text(check['reason'])
    require(check['scope'] in ('task', 'milestone', 'final'), "invalid check scope")
    require(check['producer'] in ('controller_subprocess', 'model_report'), "invalid evidence producer")
    require(check['status'] in ('required', 'passed', 'failed', 'irrelevant_skipped', 'unset'), "invalid check status")
    require(type(check['executed']) is bool, "invalid execution flag")
    if check['status'] == 'unset':
        require(check['command'] is None and not check['executed'] and check['exit_code'] is None, "unset is not passed")
    else:
        text(check['command']); digest(check['state_sha256'])
    if check['status'] in ('passed', 'failed'):
        require(check['executed'], "check was not executed")
        require(check['exit_code'] is None or type(check['exit_code']) is int, "invalid exit code")
        require((check['exit_code'] == 0) == (check['status'] == 'passed'), "check outcome mismatch")
    else:
        require(not check['executed'] and check['exit_code'] is None, "invalid pending/skipped evidence")
    return check


def evidence_satisfies(check, state_sha256):
    validate_evidence(check)
    return (check['producer'] == 'controller_subprocess' and check['status'] == 'passed'
            and check['state_sha256'] == state_sha256)


def validate_state(state):
    obj(state, ('version', 'project', 'configuration', 'models', 'tasks', 'attempts', 'status'), ('controller',))
    require(type(state['version']) is int and state['version'] == STATE_VERSION, "incompatible state; read status then explicitly reconcile/archive")
    text(state['project']); text(state['status']); validate_models(state['models'])
    require(isinstance(state['configuration'], dict) and state['configuration'], "configuration fingerprint required")
    for key, value in state['configuration'].items():
        text(key); digest(value)
    require(isinstance(state['tasks'], list) and isinstance(state['attempts'], list), "task/attempt lists required")
    seen = set()
    for task in state['tasks']:
        obj(task, ('id', 'status', 'depends_on', 'execution_model'),
            ('title', 'instructions', 'approval_required', 'selection_context', 'result'))
        text(task['id']); require(task['id'] not in seen, "duplicate task")
        require(task['status'] in ('pending', 'running', 'completed', 'failed', 'interrupted', 'approval_required'), "invalid task status")
        require(isinstance(task['depends_on'], list) and all(isinstance(x, str) and x in seen for x in task['depends_on']), "dependencies must precede task")
        execution_override(state['models'], task['execution_model']); seen.add(task['id'])
    for attempt in state['attempts']:
        validate_usage(attempt)
    return state


def read_status(path):
    """Read old/new state without migration, write, replacement, or task replay."""
    state = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    require(isinstance(state, dict), "state object required")
    compatible = False
    try:
        validate_state(state); compatible = True
    except ContractError:
        pass
    return {'version': state.get('version'), 'status': state.get('status'), 'compatible': compatible,
            'resume_allowed': False, 'action': 'explicit resume validation' if compatible else
            'read with original runtime; preserve reports/completed tasks; explicitly reconcile and archive before a separate new workflow'}


def resumable_tasks(state, project, configuration):
    validate_state(state)
    require(state['project'] == project and state['configuration'] == configuration, "project/config changed; explicit reconciliation required")
    require(all(t['status'] in ('pending', 'completed') for t in state['tasks']), "uncertain/partial edits; inspect and explicitly reconcile before resume")
    completed = {t['id'] for t in state['tasks'] if t['status'] == 'completed'}
    return [copy.deepcopy(t) for t in state['tasks'] if t['status'] == 'pending' and set(t['depends_on']) <= completed]
