"""Explicit, resumable sequential project workflow. No agents or API clients."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import run as runner
from runtime_safety import private_write, redact, summary


def save(path, state):
    private_write(path, json.dumps(redact(state), ensure_ascii=False, indent=2))


@contextmanager
def locked(project):
    directory = project / '.ai/project-workflow'
    # Do not write workflow state through links/junctions outside the project.
    for path in (project / '.ai', directory):
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('workflow directory must not be a link or reparse point')
    directory.mkdir(parents=True, exist_ok=True)
    for leaf in ('lock', 'state.json'):
        path = directory / leaf
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('workflow file must not be a link or reparse point')
    with (directory / 'lock').open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('another project workflow is active') from error
        try:
            yield directory / 'state.json'
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def configuration(project):
    files = ['.ai/models.yaml', '.ai/routing.yaml', '.ai/verification.yaml', '.ai/sev.json']
    hashes = {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in files}
    settings, _ = runner.config_from(project / '.ai/verification.yaml')
    commands = settings.get('commands', {})
    if not isinstance(commands, dict) or any(c is not None and
            (not isinstance(c, str) or not c.strip() or '\n' in c or '\r' in c) for c in commands.values()):
        raise ValueError('invalid configured verification commands')
    if redact(commands) != commands:
        raise ValueError('inline credentials are forbidden in verification commands')
    sev = json.loads((project / '.ai/sev.json').read_text(encoding='utf-8-sig'))
    if any(not isinstance(sev.get(k), str) or not sev[k] for k in ('python', 'runner', 'service', 'state')):
        raise ValueError('SEV installation paths are missing')
    # This script ships alongside the configured quick runner, sharing its implementation.
    if Path(sev['runner']).resolve() != Path(runner.__file__).resolve():
        raise ValueError('use project.py beside the configured SEV runner; reinstall to update')
    return hashes, commands, sev


def validate_plan(plan, require_scope=False):
    if not isinstance(plan, dict) or set(plan) != {'tasks'} or not isinstance(plan['tasks'], list) or not 1 <= len(plan['tasks']) <= 50:
        raise ValueError('plan must contain 1..50 tasks')
    ids = set()
    for task in plan['tasks']:
        if not isinstance(task, dict) or set(task) not in ({'id', 'title', 'instructions', 'depends_on', 'approval_required'}, {'id', 'title', 'instructions', 'depends_on', 'approval_required', 'selection_context'}):
            raise ValueError('invalid task fields')
        if require_scope or 'selection_context' in task:
            context = task.get('selection_context')
            if not isinstance(context, dict) or set(context) != {'facts', 'risks', 'dependencies'}:
                raise ValueError('task requires selection_context facts/risks/dependencies')
            for values in context.values():
                if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
                    raise ValueError('selection context must contain lists of nonempty strings')
        name = task['id']
        if not isinstance(name, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}', name) or name in ids or name == 'plan':
            raise ValueError('invalid or duplicate task id')
        ids.add(name)
        if any(not isinstance(task[k], str) or not task[k].strip() for k in ('title', 'instructions')):
            raise ValueError('task needs title and actionable instructions')
        deps = task['depends_on']
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps) or len(set(deps)) != len(deps) or type(task['approval_required']) is not bool:
            raise ValueError('invalid task dependencies or approval flag')
    done = set()
    while len(done) < len(ids):
        ready = {t['id'] for t in plan['tasks'] if t['id'] not in done and set(t['depends_on']) <= done}
        if not ready:
            raise ValueError('cyclic or unknown task dependency')
        done.update(ready)
    return plan['tasks']


def remaining(state):
    return state['max_seconds'] - state['elapsed_seconds']


def selection_scope(state, target, previous=None):
    """No inferred risk filtering: planner-authored relevant facts plus complete task."""
    context = target['selection_context']
    task = target['title'] + '\n' + target['instructions']
    facts = dict(context, depends_on=target['depends_on'], approval_required=target['approval_required'])
    if previous:
        # Retry diagnosis is relevant, but CLI usage and historical execution prompts are not.
        report = previous.get('report', {})
        outcomes = [a.get('outcome') for a in report.get('attempts', []) if a.get('outcome')]
        facts['previous_attempt'] = dict(status=previous.get('status'), error=previous.get('error') or report.get('error'),
            outcomes=outcomes, verification=previous.get('verification', report.get('verification', {})))
    return dict(task=task, facts=json.dumps(facts, ensure_ascii=False))


def model_call(project, state, sev, task, write):
    with tempfile.TemporaryDirectory(prefix='project-task-') as temp:
        task_file, facts_file = Path(temp) / 'task.txt', Path(temp) / 'facts.txt'
        private_write(task_file, task)
        private_write(facts_file, state['facts'])
        scope = state['attempts'][-1].get('selection_scope') if state.get('attempts') else None
        selection_file, selection_facts = None, None
        if scope:
            selection_file, selection_facts = Path(temp) / 'selection-task.txt', Path(temp) / 'selection-facts.txt'
            private_write(selection_file, scope['task'])
            private_write(selection_facts, scope['facts'])
        allowance = remaining(state)
        return runner.run(SimpleNamespace(project=str(project), models=project / '.ai/models.yaml',
            task_file=task_file, context_file=facts_file, selection_task_file=selection_file,
            selection_context_file=selection_facts, model=state['model'], selector='sev',
            local_python=sev['python'], local_script=sev['service'], sev_state=sev['state'],
            codex=state['codex'], selection_timeout=min(90, allowance),
            execution_deadline=time.monotonic() + allowance, write=write, allow_escalation=False,
            verification_owner='controller'))


def real_checks(project, commands, deadline):
    checks = runner.verification_report(commands, [])
    for check in checks.values():
        check['evidence_source'] = 'workflow_configuration'
    for name, command in commands.items():
        if command is None:
            continue
        allowance = deadline - time.monotonic()
        if allowance <= 0:
            checks[name].update(status='not_executed', evidence='time budget exhausted')
            break
        # PowerShell -Command otherwise collapses native nonzero exits to 1.
        windows_command = ("$ErrorActionPreference = 'Stop'\n$global:LASTEXITCODE = $null\n" + command +
            '\n$workflowCommandSucceeded = $?\n'
            'if ($null -ne $global:LASTEXITCODE) { exit $global:LASTEXITCODE }\n'
            'if (-not $workflowCommandSucceeded) { exit 1 }')
        invocation = (['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', windows_command]
                      if os.name == 'nt' else ['/bin/sh', '-c', command])
        try:
            result = subprocess.run(invocation, cwd=project, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=allowance, shell=False)
            checks[name].update(executed=True, exit_code=result.returncode,
                status='passed' if result.returncode == 0 else 'failed',
                evidence=redact((result.stdout + result.stderr)[-16000:]) or '(no output)',
                evidence_source='workflow_subprocess')
        except subprocess.TimeoutExpired:
            checks[name].update(executed=True, status='failed', exit_code=None,
                                evidence='configured check timed out', evidence_source='workflow_subprocess')
        if checks[name]['status'] == 'failed':
            break
    return checks


PLANNING = '''Plan this explicitly requested project workflow. Explore relevant project files
read-only; do not implement, run checks, invoke a runner or launch agents. Return a
completed structured outcome with summary containing ONLY a JSON object:
{"tasks":[{"id":"setup","title":"...","instructions":"...",
"depends_on":[],"approval_required":false,
"selection_context":{"facts":[],"risks":[],"dependencies":[]}}]}.
For each task, include selection_context with relevant project facts/constraints,
risks (including architecture, cross-subsystem, security, uncertainty, impact and
rework), and dependency interfaces/assumptions needed to judge that task. These are
used with the COMPLETE task instructions for model selection. Carry forward applicable
goal-level constraints and risks; do not copy unrelated goal/history or minimize risks
to obtain a cheaper model. Empty lists are valid only when nothing applies. Unknown
interfaces or unresolved design decisions must be stated as uncertainty. Acceptance
criteria belong in instructions. The execution model still receives full goal/history/facts.
Use 1..50 concrete tasks; choose the smallest useful dependency-aware decomposition.
Include acceptance criteria in instructions. Mark deployment, publishing, destructive
or externally visible actions approval_required=true. Each task will execute serially
in the same workspace through SEV. The controller runs all configured checks after
each task; report them unexecuted with that reason. Put no supplemental names in verification.
Goal:
'''


def advance(project, path, state, commands, sev, write, approve=None, retry=None):
    if approve:
        if approve not in {t['id'] for t in state['tasks']}:
            raise ValueError('unknown approval task id')
        if approve not in state['approved']:
            state['approved'].append(approve)
    if retry:
        target = state if retry == 'plan' else next((t for t in state['tasks'] if t['id'] == retry), None)
        key = 'plan_status' if retry == 'plan' else 'status'
        if target is None or target[key] not in ('running', 'failed', 'blocked', 'unresolved'):
            raise ValueError('retry requires a stopped or interrupted task (or plan)')
        if key == 'status' and target[key] == 'blocked':
            target['approval_required'] = True
        target[key] = 'pending'
    while True:
        if state['plan_status'] != 'completed':
            target, key, name = state, 'plan_status', 'plan'
        else:
            stopped = next((t for t in state['tasks'] if t['status'] not in ('pending', 'completed')), None)
            if stopped:
                state.update(status='stopped', reason='inspect workspace and explicitly --retry ' + stopped['id'])
                break
            completed = {t['id'] for t in state['tasks'] if t['status'] == 'completed'}
            target = next((t for t in state['tasks'] if t['status'] == 'pending' and set(t['depends_on']) <= completed), None)
            if target is None:
                if not state['tasks'] or len(completed) != len(state['tasks']):
                    raise ValueError('saved plan has incomplete tasks without a ready dependency')
                state.update(status='completed', reason='all tasks and configured checks completed')
                break
            key, name = 'status', target['id']
        if target[key] != 'pending':
            state.update(status='stopped', reason='inspect workspace and explicitly --retry ' + name)
            break
        if name != 'plan' and (not write or (target['approval_required'] and name not in state['approved'])):
            state.update(status='approval_required', reason='resume with --write' if not write else 'approval required: --approve ' + name)
            break
        if state['runs'] >= state['max_runs'] or remaining(state) <= 0:
            state.update(status='budget_exhausted', reason='extend --max-runs or --max-seconds explicitly on resume')
            break
        state['runs'] += 1
        target[key] = 'running'
        state.update(status='running', reason='executing ' + name)
        attempt = {'task': name, 'status': 'running', 'started_at': time.time()}
        state['attempts'].append(attempt)
        save(path, state)  # A crash leaves running, never silently replays edits.
        started = time.monotonic()
        deadline = started + remaining(state)
        try:
            previous = next((a for a in reversed(state['attempts'][:-1]) if a['task'] == name), None)
            request = PLANNING + state['goal'] if name == 'plan' else (
                'Execute only this project task; prior completed dependencies are already in the workspace.\n'
                'Do not invoke project/quick runners or agents. Do not edit workflow state or configuration.\n'
                'The controller runs configured checks after this task. Report them unexecuted with this reason; '
                'put any supplemental checks in summary. Stop and return blocked if new approval is needed.\n'
                'Overall goal:\n' + state['goal'] + '\nCompleted tasks:\n' +
                json.dumps([t for t in state['tasks'] if t['status'] == 'completed'], ensure_ascii=False) +
                '\nExplicit user approval for this task: ' + str(name in state['approved']) +
                '\nPrevious attempt (inspect existing edits before retry):\n' + json.dumps(previous, ensure_ascii=False) +
                '\nCurrent task:\n' + json.dumps(target, ensure_ascii=False))
            if name != 'plan':
                attempt['selection_scope'] = selection_scope(state, target, previous)
                save(path, state)
            report = model_call(project, state, sev, request, name != 'plan')
            attempt['report'] = report
            if report['status'] != 'awaiting_verification':
                target[key] = report['status'] if report['status'] in ('blocked', 'unresolved') else 'failed'
                if name != 'plan' and target[key] == 'blocked':
                    target['approval_required'] = True
                    if name in state['approved']:
                        state['approved'].remove(name)
            elif configuration(project)[0] != state['configuration']:
                raise ValueError('configuration changed during task; review before continuing')
            elif name == 'plan':
                tasks = validate_plan(json.loads(report['attempts'][-1]['outcome']['summary']), require_scope=True)
                state['tasks'] = [dict(t, status='pending') for t in tasks]
                target[key] = 'completed'
            else:
                checks = real_checks(project, commands, deadline)
                attempt['verification'] = checks
                target[key] = 'completed' if all(c['status'] in ('passed', 'unset') for c in checks.values()) else 'failed'
                if not any(c is not None for c in commands.values()):
                    target[key] = 'unresolved'
                    attempt['error'] = 'no configured checks; cannot claim verified project completion'
            attempt['status'] = target[key]
        except (KeyboardInterrupt, Exception) as error:
            attempt.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=str(error))
            target[key] = 'running' if isinstance(error, KeyboardInterrupt) else 'failed'
            state.update(status='stopped', reason='inspect workspace and explicitly --retry ' + name)
            save(path, state)
            raise
        finally:
            elapsed = time.monotonic() - started
            attempt['elapsed_seconds'] = elapsed
            state['elapsed_seconds'] += elapsed
            save(path, state)
    save(path, state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'resume', 'status'])
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--goal-file', type=Path)
    parser.add_argument('--context-file', type=Path)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--model', choices=['worker', 'main'])
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--max-runs', type=int)
    parser.add_argument('--max-seconds', type=float)
    parser.add_argument('--approve', help='explicit approval for one planned task')
    parser.add_argument('--retry', help='explicit reconciliation/retry of stopped task id or plan')
    args = parser.parse_args(argv)
    try:
        project = args.project.resolve(strict=True)
        with locked(project) as path:
            if args.action == 'status':
                state = json.loads(path.read_text(encoding='utf-8'))
            else:
                hashes, commands, sev = configuration(project)
                if args.action == 'start':
                    if path.exists():
                        raise ValueError('workflow exists; resume it or archive its directory before starting another')
                    if not args.goal_file:
                        raise ValueError('start requires --goal-file')
                    goal = redact(args.goal_file.read_text(encoding='utf-8-sig'))
                    if not goal.strip():
                        raise ValueError('goal is empty')
                    state = dict(version=2, project=str(project), goal=goal,
                        facts=redact(args.context_file.read_text(encoding='utf-8-sig')) if args.context_file else '',
                        configuration=hashes, commands=commands, model=args.model, codex=args.codex,
                        max_runs=20, max_seconds=3600, runs=0, elapsed_seconds=0,
                        plan_status='pending', tasks=[], attempts=[], approved=[], status='pending', reason='',
                        app_chat_model_changed=False)
                else:
                    state = json.loads(path.read_text(encoding='utf-8'))
                    if state['version'] != 2 or state['project'] != str(project) or state['configuration'] != hashes:
                        raise ValueError('workflow schema/project/configuration changed; reconcile and archive state before a new start')
                    if state['plan_status'] == 'completed':
                        validate_plan({'tasks': [{k: v for k, v in t.items() if k != 'status'} for t in state['tasks']]}, require_scope=True)
                    if args.model is not None and args.model != state['model']:
                        raise ValueError('resume retains the original model override')
                    for attempt in state['attempts']:
                        if 'elapsed_seconds' not in attempt:
                            # Conservative charge after a hard crash, including downtime.
                            elapsed = max(0, time.time() - attempt['started_at'])
                            attempt['elapsed_seconds'] = elapsed
                            state['elapsed_seconds'] += elapsed
                for key in ('max_runs', 'max_seconds'):
                    value = getattr(args, key)
                    if value is not None:
                        if value <= 0 or (key == 'max_seconds' and not math.isfinite(value)):
                            raise ValueError('budgets must be positive finite values')
                        state[key] = value
                state = advance(project, path, state, commands, sev, args.write, args.approve, args.retry)
            print(json.dumps(summary(state), ensure_ascii=True, indent=2))
            return 0 if args.action == 'status' or state['status'] == 'completed' else 1
    except (OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
        print(json.dumps(redact({'status': 'stopped', 'error': str(error), 'app_chat_model_changed': False})), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
