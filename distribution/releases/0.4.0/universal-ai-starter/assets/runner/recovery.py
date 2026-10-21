"""Reviewed, sequential recovery. Model prose is never capability evidence."""
import copy
import hashlib
import subprocess

from rev import contracts as c
from .runtime_safety import redact

CATEGORIES = ('environment', 'transient', 'code', 'plan')
DEFAULT = dict(sequence={'worker': 'main', 'main': None},
               models=dict(c.MODELS), max_retries=1, max_escalations=1,
               max_replans=1, max_tokens=None)


class Failure(RuntimeError):
    def __init__(self, category, cause, action):
        c.require(category in CATEGORIES, 'invalid failure category')
        self.kind = category
        self.action = action
        super().__init__(cause + '; action: ' + action)


def classify(error):
    if isinstance(error, Failure):
        return error.kind
    if isinstance(error, (KeyboardInterrupt, TimeoutError, subprocess.TimeoutExpired)):
        return 'transient'
    if isinstance(error, OSError):
        return 'environment'
    # Rev failures always stop locally, never imply coding incapability.
    if getattr(error, 'kind', None) == 'timeout':
        return 'transient'
    if getattr(error, 'kind', None) is not None:
        return 'environment'
    return 'code'  # Includes uncertain defects; NOT confirmed capability.


def policy(value=None):
    value = copy.deepcopy(DEFAULT if value is None else value)
    c.obj(value, tuple(DEFAULT))
    c.require(isinstance(value['models'], dict) and isinstance(value['sequence'], dict), 'invalid recovery mapping')
    c.require(all(value['models'].get(k) == v for k, v in c.MODELS.items()), 'recovery must preserve execution model mapping')
    for role, model in value['models'].items():
        c.text(role); c.text(model)
    c.require(len(set(value['models'].values())) == len(value['models']), 'recovery roles require distinct requested models')
    c.require(set(value['sequence']) == set(value['models']), 'recovery sequence must cover configured roles')
    for role in value['sequence']:
        seen = set()
        while role is not None:
            c.require(role in value['sequence'] and role not in seen, 'invalid/cyclic recovery sequence')
            seen.add(role); role = value['sequence'][role]
    c.require(value['sequence'].get('worker') in (None, 'main'), 'worker can escalate only to main')
    c.require(value['sequence'].get('main') in (None, 'escalation'), 'main can escalate only to escalation')
    c.require(set(value['models']) <= {'worker', 'main', 'escalation'} and value['sequence'].get('escalation') is None,
              'only configured worker/main/escalation sequence is supported')
    for key in ('max_retries', 'max_escalations', 'max_replans'):
        c.number(value[key], integer=True)
    c.number(value['max_tokens'], nullable=True, integer=True)
    return value


def workspace_digest(workspace):
    return hashlib.sha256(c.json_bytes(dict(sorted(workspace.items())))).hexdigest()


def check_category(checks):
    if any(x['status'] == 'required' for x in checks) or (checks and all(x['status'] == 'unset' for x in checks)):
        return 'environment'
    if any(x['status'] == 'failed' and x['executed'] and x['exit_code'] is None for x in checks):
        return 'transient'
    return 'code'  # Nonzero exit/stale evidence requires diagnosis, not capability escalation.


def review(value, record, workspace):
    c.obj(value, ('source', 'review_id', 'record', 'workspace_sha256', 'category',
                  'confirmed_capability', 'confirmed_change', 'cause', 'action',
                  'attempted_methods', 'verification_results', 'remaining_problem'))
    c.require(value['source'] == 'explicit_user_review', 'model diagnosis cannot authorize recovery')
    c.require(value['record'] == record['report_path'] and value['workspace_sha256'] == workspace_digest(workspace),
              'stale recovery review; inspect current report and partial edits')
    c.require(value['category'] in CATEGORIES and type(value['confirmed_capability']) is bool,
              'invalid typed recovery review')
    c.require(value['confirmed_change'] in (None, 'dependency', 'interface', 'design'), 'invalid plan change')
    c.require(not value['confirmed_capability'] or value['category'] == 'code', 'only analyzed code capability failure can escalate')
    c.require((value['category'] == 'plan') == (value['confirmed_change'] is not None), 'replan requires confirmed structural change')
    for key in ('review_id', 'cause', 'action', 'attempted_methods', 'verification_results', 'remaining_problem'):
        c.text(value[key])
    c.require(redact(value) == value and len(c.json_bytes(value)) <= 16384, 'secret/oversized recovery review')
    return copy.deepcopy(value)


def decision(state, task, evidence, settings):
    """Called only on explicit resume after workspace/partial-edit review."""
    meta = state['controller']
    counts = meta['recovery_counts']
    if evidence['category'] == 'plan':
        c.require(meta['mode'] == 'project', 'quick plan change requires explicit new project workflow')
        c.require(counts['replans'] < settings['max_replans'], 'replan limit exhausted; inspect reports and explicitly archive/reconcile')
        return dict(operation='replan', task=task['id'], review=evidence)
    if evidence['confirmed_capability']:
        override = meta['execution_override'] or task['execution_model'] or state['models']['execution_model']
        c.require(override is None, 'explicit user execution model prevents automatic escalation; choose a task override explicitly')
        last = next(r for r in reversed(meta['records']) if r['task'] == task['id'])
        c.require(last.get('error_kind') == 'code',
                  'environment/transient/plan failures cannot trigger capability escalation; repair the recorded cause')
        c.require(last.get('selection') is not None and last.get('model_report') is not None,
                  'no implementation model ran; repair local selection/environment without escalation')
        current = last['selection']['requested_model']
        role = next((k for k, v in settings['models'].items() if v == current), None)
        target = settings['sequence'].get(role)
        c.require(target is not None and counts['escalations'] < settings['max_escalations'],
                  'permitted escalation sequence/count exhausted; explicit user action required')
        return dict(operation='escalation', task=task['id'], model=settings['models'][target], review=evidence)
    c.require(counts['retries'] < settings['max_retries'], 'retry limit exhausted; inspect cause; explicit archive/reconciliation required')
    return dict(operation='retry', task=task['id'], review=evidence)


def token_gate(attempts, limit, next_call=True):
    if limit is None:
        return
    # Cached tokens are a subset of input, never add them twice. Unknown is not zero.
    values = [a[k] for a in attempts
              if not (a['requested_model'] == 'not_selected' and a['cli_invocations'] == 0 and a['status'] == 'failed')
              for k in ('input_tokens', 'output_tokens')]
    c.require(all(x is not None for x in values), 'token usage unknown; cannot admit another call under finite token budget')
    c.require(sum(values) < limit if next_call else sum(values) <= limit,
              'total token budget exhausted/exceeded; no further model call')


def reconcile_plan(state, tasks):
    """No new task IDs, dropped tasks, lost risks, or rewritten completion evidence."""
    old = {t['id']: t for t in state['tasks']}
    c.require(set(old) == {t['id'] for t in tasks}, 'replan cannot add/drop authorized tasks; explicit new workflow required')
    for task in tasks:
        prior = old[task['id']]
        c.require(task['execution_model'] is None, 'planner cannot create model overrides')
        if prior['status'] == 'completed':
            c.require(all(task[k] == prior[k] for k in task if k != 'execution_model'), 'replan cannot rewrite completed work')
        else:
            c.require(task['approval_required'] == prior['approval_required'], 'replan cannot change approval boundaries')
            for key, values in prior['selection_context'].items():
                c.require(set(values) <= set(task['selection_context'][key]), 'replan cannot drop task facts/risks/interfaces')
    return tasks
