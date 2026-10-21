"""Sequential controller with reviewed, bounded failure recovery."""
import copy
import hashlib
import json
import math
from pathlib import Path
import time

from rev import contracts as c
from rev.selector import Client, select
from . import codex, context, verification, recovery
from .locking import locked
from .runtime_safety import private_write, redact, reject_links
from .settings import config_from
from .workspace import snapshot, changes

STATE_DIRECTORY = '.ai/rev-workflow'
SCHEMA = 3


def configuration(project):
    """New connection is explicit; never modify/bootstrap from .ai/sev.json."""
    files = ('.ai/models.yaml', '.ai/routing.yaml', '.ai/verification.yaml', '.ai/rev.json')
    hashes = {}
    for name in files:
        path = reject_links(project / name)
        raw = path.read_bytes() if path.exists() else b'<unset>'
        hashes[name] = hashlib.sha256(raw).hexdigest()
    # A changed runtime may change contracts. Never resume it silently either.
    source = Path(__file__).resolve().parents[1]
    runtime = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for directory in ('runner', 'rev') for p in sorted((source/directory).glob('*.py'))}
    hashes['runtime_source'] = hashlib.sha256(c.json_bytes(runtime)).hexdigest()
    models, _ = config_from(project / '.ai/models.yaml')
    c.validate_models(models)
    routing, _ = config_from(project / '.ai/routing.yaml')
    c.obj(routing, ('selection', 'backend', 'automatic_recovery', 'parallel_agents'), ('recovery',))
    recovery.policy(routing.get('recovery'))
    c.require({k: v for k, v in routing.items() if k != 'recovery'} == dict(selection='rev', backend='codex_cli', automatic_recovery=False, parallel_agents=False),
              'unsupported routing; explicit Rev migration required; never silently use legacy selection')
    settings, _ = config_from(project / '.ai/verification.yaml')
    c.obj(settings, ('commands',))
    commands = settings['commands']
    c.require(isinstance(commands, dict), 'commands mapping required')
    for name, command in commands.items():
        c.text(name)
        c.require(command is None or (isinstance(command, str) and command.strip()
                  and '\n' not in command and '\r' not in command), 'invalid verification command')
    c.require(redact(commands) == commands, 'inline credentials forbidden in commands; reference environment')
    return hashes, models, commands


def write_json(path, value):
    private_write(path, json.dumps(redact(value), ensure_ascii=False, indent=2, allow_nan=False))


def validate_state(state):
    c.validate_state(state)
    meta = state.get('controller')
    c.require(isinstance(meta, dict) and meta.get('schema') == SCHEMA, 'incompatible controller schema; preserve reports and explicitly reconcile/archive')
    required = ('goal_context', 'mode', 'plan_status', 'max_calls', 'max_seconds', 'calls',
                'elapsed_seconds', 'approved', 'workspace', 'records', 'codex', 'execution_override',
                'task_overrides', 'reason', 'started_at', 'final_checks', 'milestone_checks', 'gate_status', 'gate_records',
                'recovery_counts', 'recovery_events', 'pending_recovery', 'replan_proposal', 'max_tokens')
    c.require(all(k in meta for k in required), 'incomplete controller state; explicit reconciliation required')
    c.require(meta['gate_status'] in ('pending', 'running', 'passed', 'failed'), 'invalid verification gate state')
    c.require(isinstance(meta['gate_records'], list), 'invalid gate records')
    context.validate_goal(meta['goal_context'])
    c.require(meta['mode'] in ('quick', 'project') and meta['plan_status'] in ('pending', 'running', 'completed', 'failed', 'interrupted'), 'invalid planning state')
    c.obj(meta['recovery_counts'], ('retries', 'escalations', 'replans'))
    for count in meta['recovery_counts'].values():
        c.number(count, integer=True)
    c.number(meta['max_tokens'], nullable=True, integer=True)
    c.require(isinstance(meta['recovery_events'], list), 'invalid recovery history')
    for key in ('max_calls', 'calls'):
        c.number(meta[key], integer=True)
    for key in ('max_seconds', 'elapsed_seconds', 'started_at'):
        c.number(meta[key])
    c.require(meta['max_calls'] > 0 and meta['max_seconds'] > 0, 'invalid budgets')
    c.require(isinstance(meta['workspace'], dict) and isinstance(meta['records'], list)
              and isinstance(meta['approved'], list) and isinstance(meta['task_overrides'], dict), 'invalid controller records')
    c.execution_override(state['models'], meta['execution_override'])
    for role in meta['task_overrides'].values():
        c.execution_override(state['models'], role)
    if meta['plan_status'] == 'completed':
        context.validate_plan({'tasks': [{k: t[k] for k in context.TASK_FIELDS} for t in state['tasks']]})
    c.require(len(state['attempts']) == len(meta['records']), 'attempt/detail records mismatch; explicit reconciliation required')
    for task in state['tasks']:
        if task['status'] == 'completed':
            result = task.get('result', {})
            c.require(all(k in result for k in ('handoff', 'changed_files', 'check_results', 'report_path', 'evidence')), 'completed task missing evidence; do not replay')
            context.validate_handoff(result['handoff'])
            for evidence in result['evidence']:
                c.validate_evidence(evidence)
    if state['status'] == 'completed':
        c.require(meta['gate_status'] == 'passed' and state['tasks']
                  and all(t['status'] == 'completed' for t in state['tasks']),
                  'completed state lacks controller gates; preserve evidence and reconcile/archive')
        for checks in ([meta['milestone_checks']] if meta['mode'] == 'project' else []) + [meta['final_checks']]:
            stamp = next((x['state_sha256'] for x in checks if x['status'] == 'passed'), None)
            c.require(stamp is not None and verification.satisfied(checks, stamp),
                      'completed state lacks successful controller evidence; never replay completed tasks')
    return state


def outcome_schema(planning):
    if planning:
        return context.planning_schema()
    return dict(type='object', additionalProperties=False,
                properties=dict(outcome=dict(type='string', enum=['completed', 'unresolved', 'blocked']),
                                summary=dict(type='string'), verification=dict(type='array', maxItems=0,
                                    items=dict(type='object', additionalProperties=False, properties={}, required=[])),
                                escalation=dict(type='null'),
                                handoff=dict(type='object', additionalProperties=False,
                                             properties=dict(summary=dict(type='string'), interfaces=dict(type='array', items=dict(type='string'))),
                                             required=['summary', 'interfaces'])),
                required=['outcome', 'summary', 'verification', 'escalation', 'handoff'])


def validate_outcome(outcome):
    c.obj(outcome, ('outcome', 'summary', 'verification', 'escalation', 'handoff'))
    c.require(outcome['outcome'] in ('completed', 'unresolved', 'blocked'), 'invalid outcome')
    c.text(outcome['summary'])
    c.require(outcome['verification'] == [] and outcome['escalation'] is None,
              'controller owns checks and recovery; no model-reported completion evidence')
    context.validate_handoff(outcome['handoff'])
    return outcome


class Controller:
    def __init__(self, project, backend=None, checks=None, selector=None, client_factory=None, tooling_identity=None):
        self.project = Path(project).resolve(strict=True)
        self.directory = self.project / STATE_DIRECTORY
        self.path = self.directory / 'state.json'
        self.backend = backend or codex.invoke
        self.checks = checks or verification.run_checks
        self.selector = selector or select
        self.client_factory = client_factory
        self.tooling_identity = tooling_identity
        self.evidence_cache = verification.EvidenceCache()

    def client(self, timeout):
        # Called by select only after override precedence has been resolved.
        connection = json.loads(reject_links(self.project / '.ai/rev.json').read_text(encoding='utf-8-sig'))
        return Client(connection, timeout=min(30, timeout))

    def save(self, state):
        validate_state(state)
        write_json(self.path, state)

    def recovery_policy(self):
        routing, _ = config_from(self.project / '.ai/routing.yaml')
        return recovery.policy(routing.get('recovery'))

    def start(self, goal, request=None, mode='project', execution_model=None, task_overrides=None,
              max_calls=20, max_seconds=3600, write=False, executable='codex', max_tokens=None):
        context.validate_goal(goal)
        c.require(redact(goal) == goal, 'known secret in mandatory context; remove credentials explicitly before starting')
        c.require(mode in ('quick', 'project'), 'explicit quick/project mode required')
        c.require(request is None or (mode == 'quick' and isinstance(request, str) and request.strip()),
                  'task request must be nonempty and used only by the quick path')
        c.require(type(max_calls) is int and max_calls > 0 and type(max_seconds) in (int, float)
                  and math.isfinite(max_seconds) and max_seconds > 0, 'positive finite budgets required')
        hashes, models, _ = configuration(self.project)
        c.number(max_tokens, nullable=True, integer=True)
        c.execution_override(models, execution_model)
        overrides = dict(task_overrides or {})
        for key, role in overrides.items():
            c.text(key); c.require(role in c.MODELS, 'invalid task override')
        if mode == 'quick':
            c.require(not overrides or set(overrides) == {'request'}, 'quick override task id is request')
        with locked(self.project):
            c.require(not self.path.exists(), 'workflow exists; status/resume or explicitly archive, never overwrite completed state')
            c.require(not (self.project / '.ai/project-workflow/state.json').exists(),
                      'legacy workflow exists; read status with original runtime, preserve completed work/reports, explicitly reconcile/archive before starting Rev')
            tasks = [] if mode == 'project' else [dict(context.quick_task(request or goal['goal'], overrides.get('request')), status='pending')]
            state = dict(version=4, project=str(self.project), configuration=hashes, models=models,
                         tasks=tasks, attempts=[], status='pending', controller=dict(
                             schema=SCHEMA, goal_context=copy.deepcopy(goal), mode=mode,
                             plan_status='pending' if mode == 'project' else 'completed',
                             max_calls=max_calls, max_seconds=max_seconds, calls=0, elapsed_seconds=0,
                             approved=[], workspace=snapshot(self.project), records=[], codex=executable,
                             execution_override=execution_model, task_overrides=overrides,
                             reason='', started_at=time.time(), final_checks=[], milestone_checks=[],
                             gate_status='pending', gate_records=[], max_tokens=max_tokens if max_tokens is not None else self.recovery_policy()['max_tokens'],
                             recovery_counts=dict(retries=0, escalations=0, replans=0), recovery_events=[],
                             pending_recovery=None, replan_proposal=None))
            # Validate transport context before the first model call, never drop mandatory data.
            if tasks:
                context.build(state, tasks[0])
            else:
                c.require(len(c.json_bytes(goal)) <= c.MAX_REQUEST_BYTES, 'planning goal too large; explicitly restructure without dropping constraints')
            self.save(state)
            return self.advance(state, write)

    def resume(self, write=False, approve=None, reconcile=None, max_calls=None, max_seconds=None, task_overrides=None,
               failure_review=None, accept_replan=False, max_tokens=None):
        with locked(self.project):
            state = json.loads(reject_links(self.path).read_text(encoding='utf-8-sig'))
            validate_state(state)
            hashes, models, _ = configuration(self.project)
            c.require(state['project'] == str(self.project) and hashes == state['configuration'] and models == state['models'],
                      'project/config/runtime changed; preserve reports/completed work and explicitly reconcile/archive; no automatic migration')
            meta = state['controller']
            c.require(not task_overrides or meta['pending_recovery'] is None,
                      'pending reviewed recovery exists; inspect it before changing execution override')
            c.require(not (accept_replan and (reconcile or failure_review or task_overrides or approve)),
                      'accept-replan must be a separate explicit review action')
            if meta['replan_proposal'] is not None:
                c.require(accept_replan and snapshot(self.project) == meta['workspace'],
                          'inspect private replan proposal and workspace; explicitly --accept-replan; no implementation yet')
                proposal = meta['replan_proposal']
                proposed = context.validate_plan({'tasks': proposal['tasks']})
                recovery.reconcile_plan(state, proposed)
                old = {t['id']: t for t in state['tasks']}
                meta['plan_history'] = meta.get('plan_history', []) + [copy.deepcopy(state['tasks'])]
                state['tasks'] = [copy.deepcopy(old[t['id']]) if old[t['id']]['status'] == 'completed' else
                                  dict(t, execution_model=old[t['id']]['execution_model'], status=old[t['id']]['status']) for t in proposed]
                meta['replan_proposal'] = None
                meta['recovery_events'].append(dict(operation='accept_replan', report_path=proposal['report_path']))
            else:
                c.require(not accept_replan, 'no reviewed replan proposal to accept')
            if approve is not None:
                task = next((t for t in state['tasks'] if t['id'] == approve), None)
                c.require(task is not None and task['status'] == 'approval_required', 'approval must name a waiting task')
            # An explicit reconciliation names exactly one uncertain task (or plan), never a completed task.
            stopped = [t for t in state['tasks'] if t['status'] in ('running', 'failed', 'interrupted')]
            uncertain_plan = meta['plan_status'] in ('running', 'failed', 'interrupted')
            uncertain_gate = meta['gate_status'] in ('running', 'failed')
            if stopped or uncertain_plan:
                expected = 'plan' if uncertain_plan else stopped[0]['id']
                c.require(reconcile == expected and len(stopped) <= 1,
                          'uncertain/partial edits; inspect private report and workspace, then explicitly --reconcile ' + expected)
                settings = self.recovery_policy()
                previous = None if uncertain_plan else next(r for r in reversed(meta['records']) if r['task'] == expected)
                if previous and previous.get('operation') == 'replan':
                    c.require(failure_review is not None and failure_review.get('category') == 'plan',
                              'failed/interrupted replan leaves old plan uncertain; inspect and explicitly review structural change; never execute stale plan')
                if failure_review is not None:
                    c.require(not uncertain_plan and not task_overrides and meta['pending_recovery'] is None,
                              'review must name a stopped implementation; cannot combine override or pending recovery')
                    evidence = recovery.review(failure_review, previous, snapshot(self.project))
                    pending = recovery.decision(state, stopped[0], evidence, settings)
                else:
                    c.require(meta['recovery_counts']['retries'] < settings['max_retries'], 'retry limit exhausted; inspect reports; explicit archive/reconciliation required')
                    pending = dict(operation='retry', task=expected)
                    if not uncertain_plan and not task_overrides:
                        previous = next(r for r in reversed(meta['records']) if r['task'] == expected)
                        if previous.get('selection') and previous.get('model_report'):
                            pending['model'] = previous['selection']['requested_model']
                c.require(meta['pending_recovery'] is None, 'uncertain recovery must be inspected; explicitly archive/reconcile, no automatic replay')
                meta['pending_recovery'] = pending
                # A killed parent may have no final usage/time. Charge a conservative elapsed bound;
                # unknown tokens and unknown backend requests remain unknown.
                if meta.get('active_started_at') is not None:
                    meta['elapsed_seconds'] += max(0, time.time() - meta['active_started_at'])
                    meta['active_started_at'] = None
                if uncertain_plan:
                    meta['plan_status'] = 'pending'
                else:
                    stopped[0]['status'] = 'pending'
                meta['workspace'] = snapshot(self.project)
            elif uncertain_gate:
                c.require(failure_review is None, 'gate recovery only repeats checks; no capability escalation or replan')
                c.require(reconcile == 'verification',
                          'inspect gate report and possible check edits; explicitly --reconcile verification; no task replay')
                if meta.get('active_started_at') is not None:
                    meta['elapsed_seconds'] += max(0, time.time() - meta['active_started_at'])
                    meta['active_started_at'] = None
                meta['workspace'] = snapshot(self.project)
                meta['gate_status'] = 'pending'
            else:
                c.require(failure_review is None, 'failure review requires explicit stopped-task reconciliation')
                c.require(reconcile is None, 'cannot reconcile/replay a completed or pending task')
                c.require(snapshot(self.project) == meta['workspace'],
                          'workspace changed outside controller; inspect and explicitly reconcile/archive; completed tasks are never replayed')
            if approve is not None:
                if approve not in meta['approved']:
                    meta['approved'].append(approve)
                task['status'] = 'pending'
            for name, role in (task_overrides or {}).items():
                target = next((t for t in state['tasks'] if t['id'] == name), None)
                c.require(target is not None and target['status'] in ('pending', 'approval_required') and role in c.MODELS,
                          'explicit task override must name uncompleted reconciled/pending work')
                meta.setdefault('override_events', []).append(dict(task=name, previous=target['execution_model'],
                                                                  execution_model=role, time=time.time()))
                meta['task_overrides'][name] = role
                target['execution_model'] = role
            for key, value in (('max_calls', max_calls), ('max_seconds', max_seconds), ('max_tokens', max_tokens)):
                if value is not None:
                    c.require(type(value) in ((int,) if key in ('max_calls', 'max_tokens') else (int, float))
                              and math.isfinite(value) and value > 0, 'positive finite budget required')
                    meta[key] = value
            # Read/resume of an already completed workflow never replays work or checks.
            if state['status'] == 'completed':
                commands = configuration(self.project)[2]
                verification.validate_results(meta['final_checks'], commands, 'final')
                if meta['mode'] == 'project':
                    verification.validate_results(meta['milestone_checks'], commands, 'milestone')
                return state
            self.save(state)
            return self.advance(state, write)

    def advance(self, state, write):
        meta = state['controller']
        while True:
            hashes, _, commands = configuration(self.project)
            c.require(hashes == state['configuration'], 'configuration changed; stop and explicitly reconcile/archive')
            planning = meta['plan_status'] != 'completed'
            completed = {t['id'] for t in state['tasks'] if t['status'] == 'completed'}
            task = None if planning else next((t for t in state['tasks'] if t['status'] == 'pending' and set(t['depends_on']) <= completed), None)
            if not planning and task is None:
                if state['tasks'] and len(completed) == len(state['tasks']):
                    return self.finish_gates(state, commands)
                else:
                    state['status'] = 'stopped'
                    meta['reason'] = 'waiting for approval or explicit partial-edit reconciliation'
                self.save(state)
                return state
            if not planning and (not write or (task['approval_required'] and task['id'] not in meta['approved'])):
                if write:
                    task['status'] = 'approval_required'
                state['status'] = 'approval_required'
                meta['reason'] = 'explicit --approve ' + task['id'] if write else 'source execution requires explicit --write'
                self.save(state)
                return state
            if meta['calls'] >= meta['max_calls'] or meta['elapsed_seconds'] >= meta['max_seconds']:
                state['status'] = 'budget_exhausted'; meta['reason'] = 'explicit resume budget extension required'
                self.save(state)
                return state
            try:
                recovery.token_gate(state['attempts'], meta['max_tokens'])
            except c.ContractError as error:
                state['status'] = 'budget_exhausted'; meta['reason'] = str(error)
                self.save(state)
                return state
            self.execute(state, task, commands, planning)
            if state['status'] != 'pending':
                return state

    def check_stamp(self, state):
        return verification.fingerprint(snapshot(self.project), state['configuration'],
                                        dict(environment=verification.environment_identity(),
                                             tooling=self.tooling_identity))

    def check_gate(self, state, commands, deadline, stamp, scope):
        # Reuse only independently attested, identical inputs and the SAME scope.
        checks = self.evidence_cache.get(stamp, commands, scope, self.tooling_identity)
        cached = checks is not None
        if checks is None:
            checks = self.checks(self.project, commands, deadline, stamp, scope)
        verification.validate_results(checks, commands, scope)
        c.require(configuration(self.project)[0] == state['configuration'], 'configuration changed during checks; reconcile/archive')
        if self.check_stamp(state) == stamp and time.monotonic() < deadline:
            self.evidence_cache.put(stamp, commands, scope, self.tooling_identity, checks)
        return checks, cached

    def finish_gates(self, state, commands):
        """Project milestone and final are separate gates, never another model call.

        Completed task work is immutable on resume. Failed/interrupted gates require
        named reconciliation and repeat verification only, never implementation.
        """
        meta = state['controller']
        if meta['elapsed_seconds'] >= meta['max_seconds']:
            state['status'] = 'budget_exhausted'
            meta['reason'] = 'verification time budget exhausted; explicit resume budget extension required'
            self.save(state)
            return state
        started = time.monotonic()
        deadline = started + meta['max_seconds'] - meta['elapsed_seconds']
        record = dict(status='running', scopes=[], error=None,
                      report_path=f'{STATE_DIRECTORY}/reports/gates-{len(meta["gate_records"])+1:04d}.json')
        meta['gate_records'].append(record)
        meta['milestone_checks'] = []
        meta['final_checks'] = []
        meta['gate_status'] = 'running'
        meta['active_started_at'] = time.time()
        state['status'] = 'running'
        self.save(state)  # Interrupted verification must never silently resume.
        try:
            for scope in (('milestone', 'final') if meta['mode'] == 'project' else ('final',)):
                stamp = self.check_stamp(state)
                checks, cached = self.check_gate(state, commands, deadline, stamp, scope)
                record['scopes'].append(dict(scope=scope, checks=checks, cache_hit=cached))
                meta[scope + '_checks'] = checks
                if not verification.satisfied(checks, self.check_stamp(state)):
                    raise recovery.Failure(recovery.check_category(checks),
                        scope + ' required checks failed, unset, not executed or stale',
                        'inspect subprocess evidence; --reconcile verification repeats checks only')
                c.require(time.monotonic() < deadline, scope + ' verification time budget exhausted')
            meta['gate_status'] = 'passed'
            state['status'] = 'completed'
            meta['reason'] = 'all tasks and required controller milestone/final checks passed'
        except (Exception, KeyboardInterrupt) as error:
            record['error'] = redact(str(error))
            record['error_kind'] = recovery.classify(error)
            meta['gate_status'] = 'failed'
            state['status'] = 'stopped'
            meta['reason'] = 'verification gate failed/interrupted; inspect private report; --reconcile verification; completed tasks are not replayed'
        finally:
            meta['elapsed_seconds'] += time.monotonic() - started
            meta['active_started_at'] = None
            try:
                meta['workspace'] = snapshot(self.project)
            except OSError:
                meta['workspace'] = {}
                meta['gate_status'] = 'failed'; state['status'] = 'stopped'
                meta['reason'] = 'workspace fingerprint unavailable; inspect report; --reconcile verification'
            record['status'] = meta['gate_status']
            record['controller_elapsed_seconds'] = time.monotonic() - started
            write_json(self.project / record['report_path'], record)
            self.save(state)
        return state

    def execute(self, state, task, commands, planning):
        meta = state['controller']
        pending = meta['pending_recovery']
        c.require(pending is None or pending['task'] == ('plan' if planning else task['id']),
                  'pending recovery task mismatch; inspect/reconcile without replay')
        replan = pending is not None and pending['operation'] == 'replan'
        if replan:
            planning = True
        name = 'plan' if planning else task['id']
        if replan:
            name = task['id']
        started = time.monotonic()
        deadline = started + meta['max_seconds'] - meta['elapsed_seconds']
        before = snapshot(self.project)
        record = dict(task=name, status='running', selection=None, error=None, error_kind=None, checks=[], model_report=None,
                      report_path=f'{STATE_DIRECTORY}/reports/{len(meta["records"])+1:04d}-{name}.json')
        # Attempt is saved BEFORE selection/execution. Hard interruption never silently replays.
        phase = pending['operation'] if pending else 'planning' if planning else 'implementation'
        record['operation'] = 'replan' if replan else 'planning' if planning else 'implementation'
        if pending:
            # Reserve recovery counts before any execution; crashes cannot reset them.
            key = {'retry': 'retries', 'escalation': 'escalations', 'replan': 'replans'}[phase]
            meta['recovery_counts'][key] += 1
            record['recovery'] = copy.deepcopy(pending)
            meta['recovery_events'].append(copy.deepcopy(pending))
            meta['pending_recovery'] = None
        usage = codex.attempt(phase, c.MODELS['main'] if planning else 'not_selected')
        state['attempts'].append(usage); meta['records'].append(record)
        if planning and not replan:
            meta['plan_status'] = 'running'
        else:
            task['status'] = 'running'
        state['status'] = 'running'; meta['active_started_at'] = time.time()
        self.save(state)
        try:
            if planning:
                model = state['models']['planning_model']
                if replan:
                    prompt = context.REPLANNING + c.json_bytes(dict(goal_context=meta['goal_context'],
                        tasks=[{k: t[k] for k in (*context.TASK_FIELDS, 'status')} for t in state['tasks']],
                        completed_work=[dict(id=t['id'], handoff=t['result']['handoff'],
                            changed_files=t['result']['changed_files'], check_results=t['result']['check_results'],
                            report_path=t['result']['report_path']) for t in state['tasks'] if t['status'] == 'completed'],
                        confirmed_change=pending['review'])).decode('utf-8')
                    c.require(len(prompt.encode('utf-8')) <= c.MAX_REQUEST_BYTES,
                              'replan context too large; explicitly condense interfaces; do not discard risks')
                else:
                    prompt = context.PLANNING + c.json_bytes(meta['goal_context']).decode('utf-8')
            else:
                full = context.build(state, task, exclude_record=record)
                if pending and pending.get('review'):
                    full['task']['recovery_review'] = copy.deepcopy(pending['review'])
                    # Revalidate the full recovery handoff; never truncate mandatory risks.
                    c.score_request(full, context.INSTRUCTIONS)
                models = dict(state['models'])
                if meta['execution_override'] is not None:
                    models['execution_model'] = meta['execution_override']
                if pending and pending.get('model'):
                    record['selection'] = dict(requested_model=pending['model'], source='reviewed_' + phase)
                else:
                    record['selection'] = self.selector(full, models, task['execution_model'],
                        client_factory=self.client_factory or (lambda: self.client(max(.001, deadline-time.monotonic()))))
                model = record['selection']['requested_model']
                prompt = context.EXECUTION + c.json_bytes(dict(context=full, approved=name in meta['approved'],
                    configured_checks=commands, verification_owner='controller')).decode('utf-8')
            usage['requested_model'] = model
            c.require(time.monotonic() < deadline, 'budget exhausted during selection; no paid call')
            schema = self.directory / 'schemas' / ('plan.json' if planning else 'outcome.json')
            write_json(schema, outcome_schema(planning))
            self.save(state)
            meta['calls'] += 1
            record['call_reserved'] = True
            self.save(state)  # Conservative reservation; actual invocations tracked separately.
            response = self.backend(meta['codex'], model, self.project, prompt,
                                    max(.001, deadline-time.monotonic()), schema, not planning, usage['phase'])
            record['model_report'] = response
            c.validate_usage(response['usage'])
            usage.update({k: v for k, v in response['usage'].items() if k not in ('phase', 'requested_model')})
            # Keep measured usage BEFORE validating identity/output, even for failed calls.
            c.require(response['usage']['requested_model'] == model and response['usage']['phase'] == phase, 'backend usage identity mismatch')
            if usage['status'] != 'succeeded':
                raise recovery.Failure(response.get('failure_kind', 'code'),
                    response.get('error') or 'model call failed', 'inspect private report/partial edits; explicitly reconcile before retry')
            recovery.token_gate(state['attempts'], meta['max_tokens'], next_call=False)
            c.require(configuration(self.project)[0] == state['configuration'], 'configuration changed during model call; stop and reconcile/archive')
            output = json.loads(response['response'])
            if planning:
                c.require(snapshot(self.project) == before, 'read-only planning changed workspace; inspect before explicit reconciliation')
                tasks = context.validate_plan(output)
                c.require(all(t['execution_model'] is None for t in tasks), 'planner cannot set execution overrides; only user may pin implementation')
                c.require(set(meta['task_overrides']) <= {t['id'] for t in tasks}, 'user override references unknown planned task')
                if replan:
                    recovery.reconcile_plan(state, tasks)
                    meta['replan_proposal'] = dict(tasks=tasks, report_path=record['report_path'])
                    task['status'] = 'pending'
                    state['status'] = 'approval_required'
                    meta['reason'] = 'inspect private replan proposal; --accept-replan required; completed work preserved'
                else:
                    state['tasks'] = [dict(t, status='pending', execution_model=meta['task_overrides'].get(t['id'])) for t in tasks]
                    meta['plan_status'] = 'completed'
                    state['status'] = 'pending'
            else:
                outcome = validate_outcome(output)
                record['handoff'] = outcome['handoff']
                if outcome['outcome'] != 'completed':
                    record['error_kind'] = 'code'
                    record['error'] = 'unresolved implementation; analyze cause; capability is unconfirmed'
                    task['status'] = 'approval_required' if outcome['outcome'] == 'blocked' else 'failed'
                    if outcome['outcome'] == 'blocked':
                        task['approval_required'] = True
                        if name in meta['approved']:
                            meta['approved'].remove(name)
                    state['status'] = 'stopped'; meta['reason'] = 'inspect model report; approval or explicit reconciliation required'
                else:
                    stamp = self.check_stamp(state)
                    record['checks'], record['check_cache_hit'] = self.check_gate(state, commands, deadline, stamp, 'task')
                    verification.validate_results(record['checks'], commands, 'task')
                    c.require(configuration(self.project)[0] == state['configuration'], 'configuration changed during checks; reconcile/archive')
                    current = self.check_stamp(state)
                    if verification.satisfied(record['checks'], current) and time.monotonic() < deadline:
                        task['status'] = 'completed'
                        task['result'] = dict(handoff=outcome['handoff'], changed_files=changes(before, snapshot(self.project)),
                                              check_results=verification.concise(record['checks']), report_path=record['report_path'],
                                              evidence=record['checks'])
                        state['status'] = 'pending'
                    else:
                        record['error_kind'] = recovery.check_category(record['checks'])
                        record['error'] = 'required checks failed/missing/stale; inspect subprocess evidence; capability is unconfirmed'
                        task['status'] = 'failed'; state['status'] = 'stopped'
                        meta['reason'] = 'required checks failed, missing, unset or workspace changed; inspect report; no automatic retry'
        except (Exception, KeyboardInterrupt) as error:
            # Failed CLI usage stays attached. Partial edits always require explicit resume.
            record['error'] = redact(str(error))
            record['error_kind'] = recovery.classify(error)
            if usage['status'] == 'succeeded':
                usage['status'] = 'failed'
            elif not record.get('call_reserved'):
                usage['status'] = 'failed'  # Selection never invoked a coding CLI; token fields remain unknown.
            if planning and not replan:
                meta['plan_status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
            else:
                task['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
            state['status'] = 'stopped'; meta['reason'] = 'inspect private report and partial edits; explicit reconciliation required'
        finally:
            meta['elapsed_seconds'] += time.monotonic() - started
            meta['active_started_at'] = None
            record['controller_elapsed_seconds'] = time.monotonic() - started
            try:
                meta['workspace'] = snapshot(self.project)
                record['changed_files'] = changes(before, meta['workspace'])
            except OSError:
                meta['workspace'] = {}; state['status'] = 'stopped'
                meta['reason'] = 'workspace fingerprint unavailable; inspect before reconciliation'
            record['status'] = meta['plan_status'] if planning and not replan else task['status']
            # Full output is private; concise summaries never contain prompt/raw checks.
            write_json(self.project / record['report_path'], record)
            self.save(state)


def status(project):
    directory = Path(project)
    path = directory / STATE_DIRECTORY / 'state.json'
    if not path.exists():
        path = directory / '.ai/project-workflow/state.json'
    # Read-only even for old/incompatible state. No lock/file creation or migration.
    result = c.read_status(reject_links(path))
    state = json.loads(path.read_text(encoding='utf-8-sig'))
    try:
        validate_state(state)
    except (ValueError, TypeError, KeyError):
        result.update(compatible=False, resume_allowed=False,
                      action='preserve completed work/reports; read with original runtime; explicitly reconcile/archive before new Rev workflow')
        return result
    return concise(state, path)


def concise(state, path):
    meta = state['controller']
    last = meta['records'][-1] if meta['records'] else {}
    return redact(dict(status=state['status'], reason=meta['reason'],
                       tasks={t['id']: t['status'] for t in state['tasks']},
                       calls=meta['calls'], max_calls=meta['max_calls'], elapsed_seconds=meta['elapsed_seconds'],
                       checks=verification.concise(last.get('checks', [])),
                       milestone_checks=verification.concise(meta['milestone_checks']),
                       final_checks=verification.concise(meta['final_checks']),
                       gate_status=meta['gate_status'],
                       recovery_counts=meta['recovery_counts'],
                       recovery_workspace_sha256=recovery.workspace_digest(meta['workspace']),
                       replan_report_path=meta['replan_proposal']['report_path'] if meta['replan_proposal'] else None,
                       gate_failure=((meta['gate_records'][-1].get('error') or '')[:800]
                                     if meta['gate_records'] else None),
                       gate_report_path=meta['gate_records'][-1]['report_path'] if meta['gate_records'] else None,
                       report_path=str(path),
                       last_report_path=last.get('report_path'), last_failure=dict(kind=last.get('error_kind'),
                           message=(last.get('error') or '')[:800]),
                       key_results=(state['tasks'][-1].get('result', {}).get('handoff', {}).get('summary', '')[:600]
                                    if state['tasks'] else ''), usage=codex.aggregate(state['attempts']),
                       requested_model=state['attempts'][-1]['requested_model'] if state['attempts'] else None,
                       actual_model=state['attempts'][-1]['actual_model'] if state['attempts'] else None,
                       app_chat_model_changed=False))
