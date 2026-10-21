"""Official /score client and deliberately provisional selection policy."""
import http.client
import json
import os
import socket
import time
from urllib.parse import urlsplit

from . import contracts as c
from .errors import RevError, fail

INSTRUCTIONS = ('Select the implementation model using the complete task, goal, facts, risks, constraints, uncertainty '
                'and direct dependency interfaces. Preserve permission/payment/data-change boundaries. '
                'Choose worker only for clear, independently verifiable work with low rework risk; otherwise choose main. '
                'These are option probabilities, not coding success probabilities.')


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON field')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def token_value(name):
    token = os.environ.get(name, '')
    if len(token) < 32 or len(token) > 256 or not token.isascii() or not all(x.isalnum() or x in '-_' for x in token):
        fail('authentication', 'Set the configured token environment variable to at least 32 random ASCII token characters; never put it in arguments or reports')
    return token


class Client:
    def __init__(self, connection, timeout=30):
        c.validate_connection(connection)
        if not 0 < timeout <= 930:
            fail('configuration', 'Timeout must be within (0,930] seconds')
        self.connection, self.timeout = dict(connection), timeout

    def call(self, path, body=None):
        if path not in ('/score', '/ping', '/stop'):
            fail('protocol', 'Unsupported local operation')
        raw = c.json_bytes(body or {})
        if len(raw) > c.MAX_REQUEST_BYTES:
            fail('oversize', 'Reduce direct dependency material explicitly; mandatory context must not be truncated')
        endpoint = urlsplit(self.connection['endpoint'])
        token = token_value(self.connection['token_env'])
        transport = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=self.timeout)
        deadline = time.monotonic() + self.timeout
        try:
            transport.request('POST', path, body=raw, headers={
                'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                'X-Rev-Runtime': self.connection['runtime_id'], 'X-Rev-Lock': self.connection['lock_sha256']})
            channel = transport.sock
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            channel.settimeout(remaining)
            response = transport.getresponse()
            if response.status != 200:
                if response.status == 413:
                    fail('oversize', 'Transport bytes or official tokenizer row limit exceeded; explicitly narrow direct dependencies without truncating mandatory context')
                if response.status == 504:
                    fail('timeout', 'Rev worker deadline expired; inspect readiness/resources and explicitly restart; no fallback')
                if response.status == 403:
                    fail('authentication', 'Token/runtime identity rejected; inspect the explicitly configured local connection')
                if response.status == 503:
                    fail('readiness', 'Rev is not model-ready; inspect pinned resources and explicitly restart')
                # Never reflect a server error containing context, paths or credentials.
                fail('service', 'Rev rejected request (HTTP %d); inspect local readiness/configuration and explicitly retry' % response.status)
            chunks, size = [], 0
            # read1 closes HTTPResponse.fp on the last Content-Length byte.
            # For Connection: close that can also release the final socket
            # reference: do not touch channel again once the body is complete.
            while response.length != 0 and not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                channel.settimeout(remaining)
                block = response.read1(min(8192, c.MAX_REQUEST_BYTES + 1 - size))
                if not block:
                    break
                chunks.append(block); size += len(block)
                if size > c.MAX_REQUEST_BYTES:
                    fail('protocol', 'Oversized Rev response; stop service and inspect implementation')
            if response.length not in (None, 0):
                fail('protocol', 'Truncated Rev response; inspect local service and explicitly retry')
            if time.monotonic() >= deadline:
                raise TimeoutError()
            return strict_json(b''.join(chunks))
        except RevError:
            raise
        except (TimeoutError, socket.timeout):
            fail('timeout', 'Rev deadline expired; inspect service status, stop/restart if needed, then explicitly retry; no model fallback')
        except (OSError, ValueError, http.client.HTTPException):
            fail('service', 'Rev transport/JSON failure; inspect the authenticated local service and explicitly retry')
        finally:
            transport.close()

    def ready(self):
        info = self.call('/ping')
        validate_ready(info, self.connection)
        return info


def validate_ready(info, connection):
    expected = dict(runtime_id=connection['runtime_id'], lock_sha256=connection['lock_sha256'],
                    runtime_version='0.4.0', ready=True, warmed=True,
                    model='Qwen/Qwen3.5-4B', revision='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a',
                    adapter_revision='6c0775534ff1759649aec470fc55d41c9b698219',
                    checkpoint_sha256='6417fd6b8f41449730957f827b8d009ce69d5feadaddd41951a3dff8ad772b96',
                    temperature=1.96, max_row_tokens=c.MAX_ROW_TOKENS, state_format='raw')
    if (not isinstance(info, dict) or any(type(info.get(k)) is not type(v) or info.get(k) != v for k, v in expected.items())
            or info.get('dtype') not in ('bf16', 'fp16', 'fp32')):
        fail('identity', 'Readiness/model identity mismatch; preserve state and reconcile connection; /health alone is insufficient')
    from .hardware import normalize_mode
    try:
        device, _ = normalize_mode(info.get('device'), info['dtype'])
        if device != info.get('device'):
            fail('identity', 'Readiness device must be canonical cpu or cuda:N')
    except RevError:
        fail('identity', 'Invalid readiness device/dtype')
    if type(info.get('pid')) is not int or info['pid'] <= 0:
        fail('identity', 'Readiness lacks a process identity')
    return info


def selection_policy(response):
    answer = response['answers']['execution_model']
    probabilities = answer['probabilities']
    # Provisional conservative admission, explicitly NOT fitted to coding outcomes.
    choice = answer['choice']
    if probabilities[choice] < 0.80 or abs(probabilities['worker'] - probabilities['main']) < 0.60:
        fail('abstention', 'Provisional policy abstained; inspect full task and supply an explicit execution model or revise context; no automatic fallback')
    return dict(model=choice, requested_model=c.MODELS[choice], probabilities=probabilities,
                probability_semantics='option_probabilities_not_coding_success', policy='provisional_0.80_margin_0.60',
                actual_model=None, source='local_rev')


def select(context, models, task_override=None, client_factory=None):
    override = c.execution_override(models, task_override)
    if override is not None:
        return dict(model=override, requested_model=c.MODELS[override], actual_model=None,
                    probabilities=None, source='explicit_override')
    # No constructing/loading/contacting Rev before override handling.
    try:
        body = c.score_request(context, INSTRUCTIONS)
    except c.RequestTooLarge:
        fail('oversize', 'Context exceeds transport limit; explicitly reduce direct dependency material without truncating mandatory risks/constraints')
    except c.ContractError:
        fail('input', 'Invalid or oversized context; keep all mandatory risks/constraints and explicitly reduce direct dependency material')
    if client_factory is None:
        fail('configuration', 'Provide an authenticated Rev client; paid classification/fallback is disabled')
    client = client_factory()
    client.ready()
    response = client.call('/score', body)
    try:
        c.validate_response(body, response)
        for row in response['rows']:
            if row['batch_rows'] != 1 or not 0 < row['batch_padded_tokens'] <= c.MAX_ROW_TOKENS:
                fail('protocol', 'Invalid padded-row metadata')
    except c.ContractError:
        fail('protocol', 'Malformed Rev probabilities/answers; stop and inspect runtime, never infer a fallback choice')
    return selection_policy(response)
