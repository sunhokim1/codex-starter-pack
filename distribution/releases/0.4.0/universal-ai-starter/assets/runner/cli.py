"""Explicit new-runtime CLI. Does not modify existing settings/connections."""
import argparse
import json
from pathlib import Path
import sys

from .controller import Controller, concise, status
from .runtime_safety import redact


def main(argv=None, quick=False):
    parser = argparse.ArgumentParser(description='순차 Rev 실행 컨트롤러')
    parser.add_argument('action', choices=['start', 'resume', 'status'])
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--context-file', type=Path, help='goal/facts/risks/constraints/uncertainty JSON; empty lists must be explicit')
    parser.add_argument('--task-file', type=Path, help='quick request text; default is full context goal')
    parser.add_argument('--execution-model', '--model', choices=['worker', 'main'], dest='execution_model')
    parser.add_argument('--planning-model', choices=['gpt-6.1-sol'], help='Sol planning only; never an execution override')
    parser.add_argument('--task-model', action='append', default=[], metavar='TASK=worker|main')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--approve')
    parser.add_argument('--reconcile', help='explicit partial-edit review: stopped task, plan, or verification gate; never completed work')
    parser.add_argument('--max-calls', type=int)
    parser.add_argument('--max-seconds', type=float)
    parser.add_argument('--max-tokens', type=int, help='input+output admission budget; unknown usage stops further calls')
    parser.add_argument('--failure-review', type=Path, help='explicit user cause/partial-edit review JSON; never model output')
    parser.add_argument('--accept-replan', action='store_true', help='accept inspected private proposal without changing authorization')
    parser.add_argument('--codex')
    args = parser.parse_args(argv)
    try:
        if args.action == 'status':
            print(json.dumps(status(args.project), ensure_ascii=True))
            return 0
        engine = Controller(args.project)
        overrides = {}
        for value in args.task_model:
            name, separator, role = value.partition('=')
            if not separator or not name or role not in ('worker', 'main') or name in overrides:
                raise ValueError('task-model requires unique TASK=worker|main')
            overrides[name] = role
        if args.action == 'start':
            if args.context_file is None:
                raise ValueError('start requires explicit mandatory --context-file JSON')
            if args.approve or args.reconcile or args.failure_review or args.accept_replan:
                raise ValueError('approval/reconciliation applies to an existing stopped workflow only')
            state = engine.start(json.loads(args.context_file.read_text(encoding='utf-8-sig')),
                                 request=args.task_file.read_text(encoding='utf-8-sig') if args.task_file else None,
                                 mode='quick' if quick else 'project', execution_model=args.execution_model,
                                 task_overrides=overrides, max_calls=args.max_calls if args.max_calls is not None else 20,
                                 max_seconds=args.max_seconds if args.max_seconds is not None else 3600,
                                 write=args.write, executable=args.codex or 'codex', max_tokens=args.max_tokens)
        else:
            if args.execution_model or args.planning_model or args.context_file or args.task_file or args.codex:
                raise ValueError('resume retains original goal/model overrides; changed configuration requires explicit archive/reconciliation')
            state = engine.resume(write=args.write, approve=args.approve, reconcile=args.reconcile,
                                  max_calls=args.max_calls, max_seconds=args.max_seconds, task_overrides=overrides,
                                  max_tokens=args.max_tokens, accept_replan=args.accept_replan,
                                  failure_review=json.loads(args.failure_review.read_text(encoding='utf-8-sig')) if args.failure_review else None)
        print(json.dumps(concise(state, engine.path), ensure_ascii=True))
        return 0 if state['status'] == 'completed' else 1
    except (OSError, ValueError, KeyError, TypeError, KeyboardInterrupt) as error:
        print(json.dumps(redact(dict(status='stopped', error=str(error), app_chat_model_changed=False)), ensure_ascii=True), file=sys.stderr)
        return 1
