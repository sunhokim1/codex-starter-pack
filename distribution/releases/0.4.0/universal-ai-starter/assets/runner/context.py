"""Lossless mandatory context, bounded direct interfaces, never completed history."""
import copy
import re

from rev import contracts as c
from rev.selector import INSTRUCTIONS
from .runtime_safety import redact

LISTS = ('facts', 'risks', 'constraints', 'uncertainty')
TASK_FIELDS = ('id', 'title', 'instructions', 'depends_on', 'approval_required',
               'execution_model', 'selection_context')
DEPENDENCY_LIMIT = 16384
DEPENDENCIES_LIMIT = 65536


def strings(values):
    c.require(isinstance(values, list) and all(isinstance(x, str) and x.strip() for x in values),
              'context fields must be explicit string lists (empty means none known)')
    return values


def validate_goal(goal):
    c.obj(goal, ('goal', *LISTS))
    c.text(goal['goal'])
    for key in LISTS:
        strings(goal[key])
    return goal


def validate_plan(plan):
    c.obj(plan, ('tasks',))
    c.require(isinstance(plan['tasks'], list) and 1 <= len(plan['tasks']) <= 50, 'plan needs 1..50 tasks')
    seen = set()
    for task in plan['tasks']:
        c.obj(task, TASK_FIELDS)
        c.require(isinstance(task['id'], str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', task['id'])
                  and task['id'] not in seen and task['id'] != 'plan', 'invalid/duplicate task id')
        c.text(task['title']); c.text(task['instructions'])
        deps = strings(task['depends_on'])
        c.require(len(set(deps)) == len(deps) and set(deps) <= seen, 'dependencies must precede task')
        c.require(type(task['approval_required']) is bool, 'explicit approval flag required')
        c.execution_override(dict(planning_model=c.MODELS['main'], execution_model=None), task['execution_model'])
        c.obj(task['selection_context'], (*LISTS, 'interfaces'))
        for values in task['selection_context'].values():
            strings(values)
        seen.add(task['id'])
    return plan['tasks']


def validate_handoff(handoff):
    c.obj(handoff, ('summary', 'interfaces'))
    c.text(handoff['summary']); strings(handoff['interfaces'])
    # Never silently slice a signature, constraint or risk. Request explicit condensation.
    c.require(len(c.json_bytes(handoff)) <= DEPENDENCY_LIMIT, 'handoff too large; explicitly condense interfaces, keep full private report')
    return handoff


def build(state, task, exclude_record=None):
    goal = validate_goal(state['controller']['goal_context'])
    validate_plan({'tasks': [{k: t[k] for k in TASK_FIELDS} for t in state['tasks']]})
    dependencies = []
    for name in task['depends_on']:
        source = next(t for t in state['tasks'] if t['id'] == name)
        c.require(source['status'] == 'completed', 'direct dependency is not verified complete')
        result = source['result']
        validate_handoff(result['handoff'])
        dependency = dict(id=name, **copy.deepcopy(result['handoff']),
                          changed_files=result['changed_files'], check_results=result['check_results'],
                          report_path=result['report_path'])
        c.require(len(c.json_bytes(dependency)) <= DEPENDENCY_LIMIT,
                  'direct dependency exceeds bound; explicitly reconcile concise interface/files/check summary')
        dependencies.append(dependency)
    c.require(len(c.json_bytes(dependencies)) <= DEPENDENCIES_LIMIT, 'direct dependencies exceed context budget; explicitly replan interfaces')
    scope = task['selection_context']
    context = dict(task={k: copy.deepcopy(task[k]) for k in TASK_FIELDS}, goal=goal['goal'],
                   dependencies=dependencies)
    previous = next((r for r in reversed(state['controller']['records'])
                     if r['task'] == task['id'] and r is not exclude_record), None)
    if previous is not None:
        prior = {k: copy.deepcopy(previous.get(k)) for k in
                 ('status', 'error_kind', 'error', 'handoff', 'changed_files', 'report_path')}
        prior['check_results'] = [{k: x[k] for k in ('name', 'command', 'status', 'executed', 'exit_code')}
                                 for x in previous.get('checks', [])]
        c.require(len(c.json_bytes(prior)) <= DEPENDENCY_LIMIT,
                  'previous attempt summary too large; explicitly reconcile concise evidence without dropping risks')
        context['task']['previous_attempt'] = prior
    for key in LISTS:
        # The complete goal constraints/risks survive even if the planner omitted them.
        context[key] = copy.deepcopy(goal[key]) + copy.deepcopy(scope[key])
    c.require(redact(context) == context, 'known secret in context; remove credentials explicitly, do not drop mandatory context')
    c.score_request(context, INSTRUCTIONS)  # Same full context must fit even with an execution override.
    return context


def quick_task(request, override=None):
    c.text(request)
    return dict(id='request', title='단일 요청', instructions=request, depends_on=[],
                approval_required=False, execution_model=override,
                selection_context={key: [] for key in (*LISTS, 'interfaces')})


def planning_schema():
    array = {'type': 'array', 'items': {'type': 'string'}}
    scope = {'type': 'object', 'additionalProperties': False,
             'properties': {k: copy.deepcopy(array) for k in (*LISTS, 'interfaces')},
             'required': [*LISTS, 'interfaces']}
    properties = {k: {'type': 'string'} for k in ('id', 'title', 'instructions')}
    properties.update(depends_on=array, approval_required={'type': 'boolean'},
                      execution_model={'type': ['string', 'null'], 'enum': [None, 'worker', 'main']},
                      selection_context=scope)
    task = dict(type='object', additionalProperties=False, properties=properties, required=list(TASK_FIELDS))
    return dict(type='object', additionalProperties=False,
                properties={'tasks': dict(type='array', minItems=1, maxItems=50, items=task)}, required=['tasks'])


PLANNING = '''Decompose this large goal using read-only exploration. Do not implement, run checks,
invoke runners, classify models, or launch agents. Return only the plan JSON object.
Use a compact dependency-ordered plan (normally 4..6 substantive tasks, maximum 50).
Every task must state actionable acceptance criteria and full applicable facts, risks,
constraints, uncertainties and dependency interfaces. Global mandatory context is
also preserved by the controller. Do not omit risks to obtain a cheaper model.
execution_model MUST be null: only the user can set implementation overrides.
Mark externally visible, destructive, payment, auth/ACL/startup, deployment or publishing
actions approval_required=true. Do not add actions outside the authorized goal.
The planning model does not select/pin task models. Local Rev selects each task later.
The controller owns bounded recovery; never initiate recovery calls yourself.
Goal context JSON:
'''


EXECUTION = '''Implement only the authorized current task in the existing workspace using one model.
Own exploration, design, implementation and review. Do not invoke runners or agents,
reclassify models, change workflow state/configuration, or run controller-owned checks.
Return verification=[] and escalation=null. completed means source candidate ready
for controller checks, not verified completion. Stop blocked only for a concrete new
action requiring approval; state that action. Do not replay completed dependency work.
Preserve ALL goal facts/risks/constraints/uncertainties, including approval/payment/data
boundaries. Dependencies include only direct concise interfaces; full private report
paths are available for reading, never print private state. A handoff must summarize
results and complete relevant interfaces within 16384 UTF-8 bytes; never truncate risks.
App conversation model is unchanged; requested CLI model is not confirmed actual model.
When previous_attempt is present, inspect its report and existing partial edits before
continuing. Do not blindly replay prior edits, payments or external actions.
Context JSON:
'''

REPLANNING = '''Review a confirmed dependency/interface/design change using read-only
exploration. Return only the complete plan JSON schema. Do not implement, invoke
runners/agents or checks. Preserve every authorized task ID, completed task definition,
dependency completion evidence, task facts/risks/constraints/uncertainties/interfaces,
approval flags and global mandatory context. Do not broaden authorization. Set every
execution_model to null; user overrides are retained separately. Only revise pending
work necessary for the confirmed change. This is a proposal requiring explicit user
acceptance; it cannot replace history or replay completed work. Full reports are private.
Confirmed change and existing work JSON:
'''
