"""Sequential mocked contracts, not coding quality/calibration or actual inference."""
import copy
import importlib.util
from importlib import import_module
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

BUNDLE = Path(__file__).resolve().parents[1]
ASSETS = BUNDLE / 'assets'
PACKAGE = '_rev040_controller_fixture'

# Isolate from archived runner modules and other installed packages in root discovery.
saved = {k: v for k, v in sys.modules.items() if k == 'rev' or k.startswith('rev.')}
for key in saved:
    del sys.modules[key]
spec = importlib.util.spec_from_file_location('rev', ASSETS / 'rev/__init__.py', submodule_search_locations=[str(ASSETS/'rev')])
module = importlib.util.module_from_spec(spec); sys.modules['rev'] = module; spec.loader.exec_module(module)
spec = importlib.util.spec_from_file_location(PACKAGE, ASSETS/'runner/__init__.py', submodule_search_locations=[str(ASSETS/'runner')])
module = importlib.util.module_from_spec(spec); sys.modules[PACKAGE] = module; spec.loader.exec_module(module)
controller = import_module(PACKAGE + '.controller')
context = import_module(PACKAGE + '.context')
codex = import_module(PACKAGE + '.codex')
verification = import_module(PACKAGE + '.verification')
safety = import_module(PACKAGE + '.runtime_safety')
workspace = import_module(PACKAGE + '.workspace')
recovery = import_module(PACKAGE + '.recovery')
c = import_module('rev.contracts')
RevError = import_module('rev.errors').RevError
for key in list(sys.modules):
    if key == 'rev' or key.startswith('rev.'):
        del sys.modules[key]
sys.modules.update(saved)


def goal():
    return dict(goal='한글 문서 수정 및 기존 동작 보존', facts=['기존 프로젝트 설정'],
                risks=['권한 변경', '결제', '데이터 삭제', '원인 불명 버그'],
                constraints=['승인 없는 외부 변경 금지', '비교 평가 금지'], uncertainty=['버그 원인 미확인'])


def task(name='first', deps=None, approval=False):
    value = context.quick_task('문서 변경 및 fixture 검증')
    value.update(id=name, depends_on=deps or [], approval_required=approval)
    value['selection_context'].update(facts=['관련 사실'], risks=['현재 작업 위험'],
                                      uncertainty=['현재 작업 불확실성'], interfaces=['read(path) -> text'])
    return value


def outcome(status='completed'):
    return dict(outcome=status, summary='문서 소스 수정 완료', verification=[], escalation=None,
                handoff=dict(summary='직접 결과', interfaces=['read(path) -> text']))


def backend_response(model, phase, value, failed=False):
    usage = codex.attempt(phase, model)
    usage.update(status='failed' if failed else 'succeeded', cli_invocations=1,
                 input_tokens=80, cached_input_tokens=20, output_tokens=10, elapsed_seconds=.05)
    return dict(usage=usage, response=json.dumps(value, ensure_ascii=False), error='fixture failure' if failed else None)


class Fixture:
    def __init__(self, project, plan=None, status='completed'):
        self.project = project; self.plan = plan or [task()]; self.status = status
        self.calls = []; self.contexts = []; self.checks = []; self.rev = []

    def backend(self, executable, model, project, prompt, timeout, schema, write, phase):
        self.calls.append(dict(model=model, prompt=prompt, write=write, phase=phase))
        if not write:
            return backend_response(model, phase, {'tasks': self.plan})
        # Only an isolated fixture file is changed.
        (project/'output.txt').write_text(str(len(self.calls)), encoding='utf-8')
        return backend_response(model, phase, outcome(self.status))

    def check(self, project, commands, deadline, stamp, scope):
        self.checks.append(stamp)
        return [dict(name=name, command=command, scope=scope, status='passed' if command else 'unset',
                     producer='controller_subprocess', state_sha256=stamp if command else None,
                     executed=bool(command), exit_code=0 if command else None,
                     reason='mock subprocess evidence' if command else 'unset') for name, command in commands.items()]

    def client(self):
        owner = self
        class Client:
            def ready(self):
                owner.rev.append('ready')

            def call(self, path, body):
                owner.rev.append(path); owner.contexts.append(copy.deepcopy(body['state']))
                return dict(answers={'execution_model': dict(choice='worker', probabilities=dict(worker=.95, main=.05))},
                            server_seconds=.01, path='rows', rows=[dict(gpu_seconds=.01, batch_rows=1,
                            batch_padded_tokens=150, queued_seconds=0)], generated_tokens=0)
        return Client()

    def engine(self):
        return controller.Controller(self.project, backend=self.backend, checks=self.check, client_factory=self.client)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        directory = self.project/'.ai'; directory.mkdir()
        for name in ('models.yaml', 'routing.yaml', 'verification.yaml'):
            (directory/name).write_bytes((ASSETS/'runner/templates'/name).read_bytes())
        (directory/'verification.yaml').write_text('commands:\n  test: "fixture-check"\n  lint: null\n', encoding='utf-8')
        # No ACL/auth/startup changes even on Windows fixture files.
        self.permissions = patch.object(safety, 'private_permissions', return_value=None)
        self.permissions.start(); self.addCleanup(self.permissions.stop)

    def read(self):
        return json.loads((self.project/'.ai/rev-workflow/state.json').read_text(encoding='utf-8'))

    def test_large_plan_does_not_pin_execution(self):
        fixture = Fixture(self.project, [task('a'), task('b', ['a'])])
        state = fixture.engine().start(goal(), write=True)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual([x['model'] for x in fixture.calls], ['gpt-6.1-sol', 'gpt-6-luna', 'gpt-6-luna'])
        self.assertEqual([x['write'] for x in fixture.calls], [False, True, True])
        self.assertEqual(fixture.rev.count('/score'), 2)
        self.assertEqual(len(state['attempts']), 3)
        self.assertEqual(state['controller']['calls'], 3)
        self.assertIsNone(state['models']['execution_model'])
        self.assertEqual(fixture.calls[0]['phase'], 'planning')

    def test_quick_has_no_planner_or_paid_classifier(self):
        fixture = Fixture(self.project)
        state = fixture.engine().start(goal(), mode='quick', write=True)
        self.assertEqual([x['phase'] for x in fixture.calls], ['implementation'])
        self.assertEqual(fixture.rev, ['ready', '/score'])
        self.assertEqual(state['status'], 'completed')
        self.assertNotIn('classifier', json.dumps(fixture.calls[0]['model']))

    def test_user_global_override_bypasses_rev_without_connection(self):
        fixture = Fixture(self.project)
        fixture.client = Mock(side_effect=AssertionError('Rev access forbidden'))
        state = fixture.engine().start(goal(), mode='quick', execution_model='main', write=True)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(fixture.calls[0]['model'], 'gpt-6.1-sol')
        fixture.client.assert_not_called()

    def test_task_override_wins_cli_global_and_config_global(self):
        (self.project/'.ai/models.yaml').write_text('planning_model: gpt-6.1-sol\nexecution_model: main\n')
        fixture = Fixture(self.project)
        fixture.client = Mock(side_effect=AssertionError('Rev access forbidden'))
        state = fixture.engine().start(goal(), mode='quick', execution_model='main', task_overrides={'request':'worker'}, write=True)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(fixture.calls[0]['model'], 'gpt-6-luna')
        fixture.client.assert_not_called()

    def test_cli_override_wins_config_and_preserves_planner(self):
        (self.project/'.ai/models.yaml').write_text('planning_model: gpt-6.1-sol\nexecution_model: main\n')
        fixture = Fixture(self.project)
        fixture.client = Mock(side_effect=AssertionError('Rev access forbidden'))
        state = fixture.engine().start(goal(), execution_model='worker', write=True)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual([x['model'] for x in fixture.calls], ['gpt-6.1-sol', 'gpt-6-luna'])
        fixture.client.assert_not_called()

    def test_planner_cannot_pin_implementation(self):
        planned = task(); planned['execution_model'] = 'main'
        fixture = Fixture(self.project, [planned])
        state = fixture.engine().start(goal(), write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(len(fixture.calls), 1)
        self.assertIn('planner cannot', state['controller']['records'][0]['error'])

    def test_direct_dependencies_only_full_risks_to_rev_and_execution(self):
        fixture = Fixture(self.project, [task('unrelated'), task('a'), task('b', ['a'])])
        state = fixture.engine().start(goal(), write=True)
        self.assertEqual(state['status'], 'completed')
        selected = fixture.contexts[-1]
        self.assertEqual([d['id'] for d in selected['dependencies']], ['a'])
        for key in context.LISTS:
            for value in goal()[key]:
                self.assertIn(value, selected[key])
                self.assertIn(value, fixture.calls[-1]['prompt'])
        dependency = selected['dependencies'][0]
        self.assertEqual(dependency['interfaces'], ['read(path) -> text'])
        self.assertIn('check_results', dependency)
        self.assertIn('output.txt', dependency['changed_files'])
        self.assertIn('report_path', dependency)
        self.assertNotIn('records', selected)

    def test_korean_long_document_context_keeps_uncertainty(self):
        value = goal(); value['facts'].append('문서 원문 보존. ' * 3000)
        fixture = Fixture(self.project)
        state = fixture.engine().start(value, mode='quick', write=True)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(fixture.contexts[0]['facts'][1], value['facts'][1])
        self.assertEqual(fixture.contexts[0]['uncertainty'], value['uncertainty'])

    def test_missing_context_and_oversize_rejected_before_calls(self):
        fixture = Fixture(self.project)
        missing = goal(); del missing['risks']
        with self.assertRaises(c.ContractError):
            fixture.engine().start(missing, mode='quick', write=True)
        oversized = goal(); oversized['risks'] = ['위험' * c.MAX_REQUEST_BYTES]
        with self.assertRaises(c.ContractError):
            fixture.engine().start(oversized, mode='quick', write=True)
        self.assertFalse(fixture.calls)
        self.assertFalse(fixture.rev)

    def test_dependency_oversize_rejected_not_silently_sliced(self):
        fixture = Fixture(self.project, [task('a'), task('b', ['a'])])
        state = fixture.engine().start(goal(), write=False)
        first = state['tasks'][0]
        first['status'] = 'completed'
        first['result'] = dict(handoff=dict(summary='full interface', interfaces=[]),
                              changed_files=['a'*17000], check_results=[], report_path='private/report.json')
        with self.assertRaises(c.ContractError):
            context.build(state, state['tasks'][1])

    def test_rev_error_stops_without_paid_fallback(self):
        for kind in ('timeout', 'oversize', 'service', 'abstention'):
            with self.subTest(kind=kind):
                fixture = Fixture(self.project)
                engine = fixture.engine()
                engine.selector = Mock(side_effect=RevError(kind, 'inspect service explicitly'))
                state = engine.start(goal(), mode='quick', write=True)
                self.assertEqual(state['status'], 'stopped')
                self.assertFalse(fixture.calls)
                self.assertEqual(state['controller']['records'][0]['error_kind'], 'transient' if kind == 'timeout' else 'environment')
                self.assertIn(kind, state['controller']['records'][0]['error'])
                self.assertEqual(state['attempts'][0]['requested_model'], 'not_selected')
                # New isolated fixture case; explicitly remove only its private test workflow.
                import shutil
                target = (self.project/'.ai/rev-workflow').resolve()
                self.assertTrue(target.is_relative_to(self.project))
                self.assertEqual(target, self.project/'.ai/rev-workflow')
                shutil.rmtree(target)

    def test_failed_usage_kept_and_unknown_aggregated(self):
        fixture = Fixture(self.project)
        fixture.backend = lambda exe, model, project, prompt, timeout, schema, write, phase: backend_response(model, phase, {}, failed=True)
        state = fixture.engine().start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        usage = state['attempts'][0]
        self.assertEqual(usage['input_tokens'], 80)
        self.assertEqual(usage['status'], 'failed')
        self.assertEqual(usage['cli_invocations'], 1)
        self.assertIsNone(usage['actual_model'])
        unknown = codex.attempt('implementation', 'gpt-6-luna')
        totals = codex.aggregate([usage, unknown])
        self.assertIsNone(totals['input_tokens']['total'])
        self.assertEqual(totals['input_tokens']['known_subtotal'], 80)
        self.assertEqual(totals['input_tokens']['unknown_attempts'], 1)
        self.assertIsNone(totals['backend_requests']['total'])
        self.assertIsNone(totals['app_chat_usage'])

    def test_partial_failed_cli_stream_retains_usage(self):
        stream = '\n'.join(json.dumps(x) for x in [
            {'type':'turn.failed', 'usage':dict(input_tokens=17, cached_input_tokens=2, output_tokens=3)},
            {'type':'error', 'message':'failure'}])
        result = codex.parse_output(stream)
        self.assertEqual(result['usage']['input_tokens'], 17)
        self.assertTrue(result['errors'])
        result = codex.parse_output('{invalid}\n' + stream)
        self.assertEqual(result['usage']['output_tokens'], 3)

    def test_missing_cli_usage_stays_unknown(self):
        stream = '\n'.join(json.dumps(x) for x in [
            {'type':'item.completed', 'item':dict(type='agent_message', text='{}')},
            {'type':'turn.completed'}])
        result = codex.parse_output(stream)
        self.assertFalse(result['errors'])
        self.assertTrue(all(x is None for x in result['usage'].values()))

    def test_real_invoke_protocol_mock_failure_preserves_usage(self):
        process = Mock(); process.returncode = 9
        process.communicate.return_value = (json.dumps({'type':'turn.failed', 'usage':dict(input_tokens=9, cached_input_tokens=0, output_tokens=1)}), 'failure')
        manager = Mock(); manager.__enter__ = Mock(return_value=process); manager.__exit__ = Mock(return_value=False)
        with patch.object(codex.subprocess, 'Popen', return_value=manager) as spawn:
            record = codex.invoke('fixture-codex', 'gpt-6-luna', self.project, 'context', 1, Path('schema.json'), True, 'implementation')
        self.assertEqual(record['usage']['status'], 'failed')
        self.assertEqual(record['usage']['input_tokens'], 9)
        self.assertEqual(record['usage']['cli_invocations'], 1)
        self.assertIsNone(record['usage']['backend_requests'])
        self.assertIn('--model', spawn.call_args.args[0])

    def test_budget_after_planner_stops_before_task(self):
        fixture = Fixture(self.project)
        state = fixture.engine().start(goal(), max_calls=1, write=True)
        self.assertEqual(state['status'], 'budget_exhausted')
        self.assertEqual(len(fixture.calls), 1)
        self.assertFalse(fixture.rev)
        state = fixture.engine().resume(write=True, max_calls=2)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(fixture.calls), 2)

    def test_budget_elapsed_after_selection_prevents_paid_call(self):
        fixture = Fixture(self.project)
        engine = fixture.engine()
        def slow_selector(*args, **kwargs):
            # Advance monotonic time deterministically without sleeping.
            clock.return_value = 100
            return dict(requested_model='gpt-6-luna')
        engine.selector = slow_selector
        with patch.object(controller.time, 'monotonic', return_value=0) as clock:
            state = engine.start(goal(), mode='quick', max_seconds=1, write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertFalse(fixture.calls)

    def test_approval_boundary_and_completed_no_replay(self):
        fixture = Fixture(self.project, [task('needs_approval', approval=True)])
        engine = fixture.engine()
        state = engine.start(goal(), write=True)
        self.assertEqual(state['status'], 'approval_required')
        self.assertEqual(len(fixture.calls), 1)
        self.assertFalse(fixture.rev)
        state = engine.resume(write=True, approve='needs_approval')
        self.assertEqual(state['status'], 'completed')
        engine.resume(write=True)
        self.assertEqual(len(fixture.calls), 2)
        with self.assertRaises(c.ContractError):
            engine.resume(write=True, reconcile='needs_approval')

    def test_interrupted_resume_requires_explicit_named_reconciliation(self):
        # This fixture isolates reconciliation; separate tests assert unknown-usage token stops.
        routing = self.project/'.ai/routing.yaml'
        routing.write_text(routing.read_text().replace('max_tokens: 2000000', 'max_tokens: null'))
        fixture = Fixture(self.project)
        fixture.backend = Mock(side_effect=KeyboardInterrupt())
        engine = fixture.engine()
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['tasks'][0]['status'], 'interrupted')
        before = engine.path.read_bytes()
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        self.assertEqual(before, engine.path.read_bytes())
        fixture.backend = Fixture(self.project).backend
        engine.backend = fixture.backend
        state = engine.resume(write=True, reconcile='request')
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['attempts']), 2)
        self.assertEqual(state['attempts'][1]['phase'], 'retry')

    def test_configuration_change_does_not_overwrite_or_resume(self):
        fixture = Fixture(self.project)
        engine = fixture.engine()
        engine.start(goal(), write=False)
        before = engine.path.read_bytes()
        with (self.project/'.ai/models.yaml').open('a') as stream:
            stream.write('# changed config\n')
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        self.assertEqual(before, engine.path.read_bytes())

    def test_config_change_during_execution_keeps_failed_usage(self):
        fixture = Fixture(self.project)
        original = fixture.backend
        def editing(*args):
            record = original(*args)
            with (self.project/'.ai/models.yaml').open('a') as stream:
                stream.write('# unexpected edit\n')
            return record
        engine = fixture.engine(); engine.backend = editing
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['attempts'][0]['input_tokens'], 80)
        self.assertEqual(state['attempts'][0]['status'], 'failed')
        self.assertFalse(fixture.checks)

    def test_external_workspace_edits_refuse_completed_resume(self):
        fixture = Fixture(self.project)
        engine = fixture.engine(); engine.start(goal(), mode='quick', write=True)
        before = engine.path.read_bytes()
        (self.project/'outside.txt').write_text('external edit')
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        self.assertEqual(before, engine.path.read_bytes())

    def test_model_success_and_unset_checks_are_not_completion(self):
        (self.project/'.ai/verification.yaml').write_text('commands:\n  test: null\n')
        fixture = Fixture(self.project)
        state = fixture.engine().start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['tasks'][0]['status'], 'failed')
        self.assertEqual(state['controller']['records'][0]['checks'][0]['status'], 'unset')

    def test_failed_model_reported_checks_cannot_replace_controller(self):
        fixture = Fixture(self.project)
        report = outcome(); report['verification'] = [dict(name='test', executed=True)]
        fixture.backend = lambda exe, model, project, prompt, timeout, schema, write, phase: backend_response(model, phase, report)
        state = fixture.engine().start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertFalse(fixture.checks)

    def test_old_state_read_only_and_new_start_refused(self):
        path = self.project/'.ai/project-workflow/state.json'; path.parent.mkdir()
        original = b'{"version":3,"status":"completed","tasks":[{"id":"done","status":"completed"}]}'
        path.write_bytes(original)
        info = controller.status(self.project)
        self.assertFalse(info['compatible']); self.assertFalse(info['resume_allowed'])
        self.assertEqual(path.read_bytes(), original)
        fixture = Fixture(self.project)
        with self.assertRaises(c.ContractError):
            fixture.engine().start(goal(), mode='quick', write=True)
        self.assertEqual(path.read_bytes(), original)

    def test_unknown_schema_resume_refuses_without_write(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        engine.start(goal(), write=False)
        state = self.read(); state['controller']['schema'] = 999
        engine.path.write_text(json.dumps(state), encoding='utf-8')
        before = engine.path.read_bytes()
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        self.assertEqual(before, engine.path.read_bytes())

    def test_explicit_resume_override_after_rev_failure_has_zero_rev_access(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        engine.selector = Mock(side_effect=RevError('abstention', 'explicit model required'))
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        engine.selector = controller.select
        engine.client_factory = Mock(side_effect=AssertionError('Rev must be bypassed'))
        state = engine.resume(write=True, reconcile='request', task_overrides={'request':'main'})
        self.assertEqual(state['status'], 'completed')
        engine.client_factory.assert_not_called()
        self.assertEqual(fixture.calls[0]['model'], 'gpt-6.1-sol')
        self.assertIn('previous_attempt', fixture.calls[0]['prompt'])
        self.assertIn('abstention', fixture.calls[0]['prompt'])
        self.assertEqual(state['controller']['override_events'][0]['task'], 'request')

    def test_missing_or_model_evidence_cannot_complete(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        engine.checks = lambda *args: []
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertIn('cover all', state['controller']['records'][0]['error'])
        evidence = fixture.check(self.project, {'test':'fixture-check'}, 100, 'a'*64, 'task')
        evidence[0]['producer'] = 'model_report'
        with self.assertRaises(c.ContractError):
            verification.validate_results(evidence, {'test':'fixture-check'}, 'task')

    def test_task_milestone_final_are_distinct_controller_gates(self):
        fixture = Fixture(self.project)
        scopes = []
        original = fixture.check
        def check(*args):
            scopes.append(args[-1])
            return original(*args)
        engine = fixture.engine(); engine.checks = check
        state = engine.start(goal(), write=True)
        self.assertEqual(scopes, ['task', 'milestone', 'final'])
        self.assertEqual(state['controller']['gate_status'], 'passed')
        self.assertEqual(state['controller']['final_checks'][0]['scope'], 'final')
        engine.resume(write=True)
        self.assertEqual(scopes, ['task', 'milestone', 'final'])
        self.assertEqual(len(fixture.calls), 2)

    def test_quick_final_failure_resume_checks_only_no_completed_task_replay(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        fail = [True]
        def check(*args):
            result = fixture.check(*args)
            if args[-1] == 'final' and fail[0]:
                result[0].update(status='failed', exit_code=7, reason='fixture nonzero')
            return result
        engine.checks = check
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['tasks'][0]['status'], 'completed')
        before = engine.path.read_bytes()
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        self.assertEqual(before, engine.path.read_bytes())
        fail[0] = False
        state = engine.resume(write=True, reconcile='verification')
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(fixture.calls), 1)
        self.assertEqual(len(state['controller']['gate_records']), 2)

    def test_milestone_failure_prevents_final(self):
        fixture = Fixture(self.project); engine = fixture.engine(); scopes = []
        def check(*args):
            scopes.append(args[-1]); result = fixture.check(*args)
            if args[-1] == 'milestone':
                result[0].update(status='failed', exit_code=None, reason='timed out')
            return result
        engine.checks = check
        state = engine.start(goal(), write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(scopes, ['task', 'milestone'])
        self.assertEqual(state['controller']['final_checks'], [])
        self.assertEqual(state['tasks'][0]['status'], 'completed')

    def test_all_unset_cannot_complete_model_success(self):
        (self.project/'.ai/verification.yaml').write_text('commands:\n  test: null\n  lint: null\n')
        fixture = Fixture(self.project)
        state = fixture.engine().start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['tasks'][0]['status'], 'failed')
        self.assertTrue(all(x['status'] == 'unset' for x in state['controller']['records'][0]['checks']))

    def test_check_edits_invalidate_success_and_no_cache(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        def check(*args):
            result = fixture.check(*args)
            (self.project/'check-edit.txt').write_text('changed during check')
            return result
        engine.checks = check
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertFalse(engine.evidence_cache.entries)

    def test_gate_budget_prevents_execution_and_requires_extension(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        state = engine.start(goal(), mode='quick', write=True)
        state['status'] = 'pending'; state['controller']['gate_status'] = 'pending'
        state['controller']['elapsed_seconds'] = state['controller']['max_seconds']
        engine.save(state)
        count = len(fixture.checks)
        state = engine.resume(write=True)
        self.assertEqual(state['status'], 'budget_exhausted')
        self.assertEqual(len(fixture.checks), count)
        state = engine.resume(write=True, max_seconds=7200)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(fixture.calls), 1)

    def test_checks_over_deadline_cannot_complete_even_with_mock_success(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        def check(*args):
            result = fixture.check(*args)
            clock.return_value = 100
            return result
        engine.checks = check
        with patch.object(controller.time, 'monotonic', return_value=0) as clock:
            state = engine.start(goal(), mode='quick', write=True, max_seconds=1)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['tasks'][0]['status'], 'failed')
        self.assertFalse(engine.evidence_cache.entries)

    def test_controller_schema_one_is_read_only_without_implicit_upgrade(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        engine.start(goal(), write=False)
        state = self.read(); state['controller']['schema'] = 1
        engine.path.write_text(json.dumps(state), encoding='utf-8')
        before = engine.path.read_bytes()
        self.assertFalse(controller.status(self.project)['compatible'])
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        self.assertEqual(before, engine.path.read_bytes())

    def test_gate_workspace_change_requires_explicit_reconciliation(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        original = fixture.check
        def check(*args):
            result = original(*args)
            if args[-1] == 'final':
                (self.project/'uncertain.txt').write_text('check partial edit')
                raise KeyboardInterrupt()
            return result
        engine.checks = check
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['tasks'][0]['status'], 'completed')
        (self.project/'reviewed.txt').write_text('manual review')
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        engine.checks = fixture.check
        state = engine.resume(write=True, reconcile='verification')
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(fixture.calls), 1)

    def test_workspace_digest_is_order_independent(self):
        self.assertEqual(verification.fingerprint({'a':'1','b':'2'}, {'c':'3'}),
                         verification.fingerprint({'b':'2','a':'1'}, {'c':'3'}))

    def test_existing_rev_state_not_overwritten_by_start(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        engine.start(goal(), mode='quick', write=True)
        before = engine.path.read_bytes()
        with self.assertRaises(c.ContractError):
            engine.start(goal(), mode='quick', write=True)
        self.assertEqual(engine.path.read_bytes(), before)
        self.assertEqual(len(fixture.calls), 1)

    def test_empty_or_ignored_task_request_rejected(self):
        fixture = Fixture(self.project)
        for mode, request in [('quick', ''), ('project', 'would be ignored')]:
            with self.assertRaises(c.ContractError):
                fixture.engine().start(goal(), mode=mode, request=request, write=True)
        self.assertFalse(fixture.calls)

    def test_hard_crash_usage_unknown_and_conservative_time_charge(self):
        routing = self.project/'.ai/routing.yaml'
        routing.write_text(routing.read_text().replace('max_tokens: 2000000', 'max_tokens: null'))
        fixture = Fixture(self.project); engine = fixture.engine()
        engine.start(goal(), write=False)
        state = self.read()
        state['tasks'][0]['status'] = 'running'
        state['controller']['active_started_at'] = controller.time.time() - 5
        state['attempts'].append(codex.attempt('implementation', 'gpt-6-luna'))
        state['controller']['records'].append(dict(task='first', checks=[], error=None, report_path='private/uncertain.json'))
        engine.path.write_text(json.dumps(state), encoding='utf-8')
        state = engine.resume(write=True, reconcile='first')
        self.assertEqual(state['status'], 'completed')
        self.assertGreaterEqual(state['controller']['elapsed_seconds'], 5)
        self.assertIsNone(state['attempts'][1]['input_tokens'])
        self.assertEqual(state['attempts'][2]['phase'], 'retry')
        self.assertIn('uncertain.json', fixture.calls[-1]['prompt'])

    def test_summary_omits_raw_private_context(self):
        fixture = Fixture(self.project)
        state = fixture.engine().start(goal(), mode='quick', write=True)
        console = controller.concise(state, fixture.engine().path)
        serialized = json.dumps(console, ensure_ascii=False)
        self.assertNotIn(goal()['goal'], serialized)
        self.assertNotIn('prompt', serialized)
        self.assertNotIn('stdout', serialized)
        self.assertIn('report_path', console)
        self.assertFalse(console['app_chat_model_changed'])

    def test_new_runtime_exclusions_keep_connection_config_visible(self):
        private = self.project/'.ai/rev-workflow'; private.mkdir()
        (private/'report.txt').write_text('private')
        runtime = self.project/'.rev-runtime'; runtime.mkdir()
        (runtime/'private.txt').write_text('private')
        (self.project/'.ai/rev.json').write_text('{}')
        before = workspace.snapshot(self.project)
        self.assertIn('.ai/rev.json', before)
        self.assertNotIn('.ai/rev-workflow/report.txt', before)
        self.assertNotIn('.rev-runtime/private.txt', before)

    def test_known_credentials_fail_without_sending_or_persisting(self):
        value = goal(); value['facts'] = ['api_key=sk-' + 'x'*32]
        fixture = Fixture(self.project)
        with self.assertRaises(c.ContractError):
            fixture.engine().start(value, mode='quick', write=True)
        self.assertFalse(fixture.calls)
        self.assertFalse(fixture.rev)
        self.assertFalse(fixture.engine().path.exists())


class RecoveryTests(unittest.TestCase):
    setUp = ControllerTests.setUp
    def evidence(self, state, category='code', capability=False, change=None):
        return dict(source='explicit_user_review', review_id='review-fixture',
                    record=state['controller']['records'][-1]['report_path'],
                    workspace_sha256=recovery.workspace_digest(workspace.snapshot(self.project)),
                    category=category, confirmed_capability=capability, confirmed_change=change,
                    cause='분석한 원인', action='검토 후 제한된 다음 단계', attempted_methods='시도와 원인 분석',
                    verification_results='fixture 검사 실패 확인', remaining_problem='확인된 미해결 문제')

    def failing(self, mode='quick', **kwargs):
        fixture = Fixture(self.project, status='unresolved'); engine = fixture.engine()
        state = engine.start(goal(), mode=mode, write=True, **kwargs)
        return fixture, engine, state

    def test_recovery_typed_categories_do_not_infer_capability(self):
        cases = [(OSError('missing'), 'environment'), (TimeoutError('deadline'), 'transient'),
                 (KeyboardInterrupt(), 'transient'), (ValueError('unknown'), 'code'),
                 (recovery.Failure('plan', 'interface changed', 'review'), 'plan')]
        for error, category in cases:
            self.assertEqual(recovery.classify(error), category)

    def test_recovery_capability_escalation_retains_usage_and_no_rev_reclassification(self):
        fixture, engine, state = self.failing()
        fixture.status = 'completed'
        evidence = self.evidence(state, capability=True)
        state = engine.resume(write=True, reconcile='request', failure_review=evidence)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual([x['model'] for x in fixture.calls], ['gpt-6-luna', 'gpt-6.1-sol'])
        self.assertEqual([x['phase'] for x in fixture.calls], ['implementation', 'escalation'])
        self.assertEqual(fixture.rev.count('/score'), 1)
        self.assertEqual(state['controller']['recovery_counts']['escalations'], 1)
        self.assertEqual(codex.aggregate(state['attempts'])['input_tokens']['total'], 160)
        self.assertIn('권한 변경', fixture.calls[-1]['prompt'])
        self.assertIn('시도와 원인 분석', fixture.calls[-1]['prompt'])

    def test_recovery_sequential_configured_astra_and_exhaustion(self):
        fixture, engine, state = self.failing()
        for expected in ('gpt-6.1-sol', 'gpt-6-astra'):
            state = engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, capability=True))
            self.assertEqual(fixture.calls[-1]['model'], expected)
        before = engine.path.read_bytes()
        with self.assertRaisesRegex(c.ContractError, 'exhausted'):
            engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, capability=True))
        self.assertEqual(before, engine.path.read_bytes())
        self.assertEqual(len(fixture.calls), 3)

    def test_recovery_override_prevents_escalation(self):
        fixture, engine, state = self.failing(execution_model='worker')
        with self.assertRaisesRegex(c.ContractError, 'user execution model'):
            engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, capability=True))
        self.assertEqual(len(fixture.calls), 1)
        self.assertFalse(fixture.rev)

    def test_recovery_timeout_requires_resume_no_escalation_and_failed_usage_retained(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        def timeout(*args):
            result = backend_response(args[1], args[-1], outcome(), failed=True)
            result.update(failure_kind='transient', error='deadline expired')
            (self.project/'partial.txt').write_text('partial edit')
            return result
        engine.backend = timeout
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['controller']['records'][-1]['error_kind'], 'transient')
        self.assertEqual(state['attempts'][0]['input_tokens'], 80)
        with self.assertRaisesRegex(c.ContractError, 'cannot trigger'):
            engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, capability=True))
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        engine.backend = fixture.backend
        state = engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, 'transient'))
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['attempts'][-1]['phase'], 'retry')
        self.assertEqual(state['controller']['recovery_counts']['escalations'], 0)
        self.assertEqual(state['attempts'][-1]['requested_model'], 'gpt-6-luna')

    def test_recovery_retry_exhaustion_and_no_unchanged_plan_replan(self):
        fixture, engine, state = self.failing(mode='project')
        state = engine.resume(write=True, reconcile='first', failure_review=self.evidence(state))
        self.assertEqual(len([x for x in fixture.calls if not x['write']]), 1)
        self.assertEqual(state['controller']['recovery_counts']['replans'], 0)
        with self.assertRaisesRegex(c.ContractError, 'retry limit'):
            engine.resume(write=True, reconcile='first')

    def test_recovery_model_review_stale_review_and_unconfirmed_plan_rejected(self):
        fixture, engine, state = self.failing(mode='project')
        for mutate in (dict(source='model_report'), dict(workspace_sha256='0'*64),
                       dict(category='plan'), dict(category='transient', confirmed_capability=True)):
            evidence = self.evidence(state); evidence.update(mutate)
            with self.subTest(mutate=mutate), self.assertRaises(c.ContractError):
                engine.resume(write=True, reconcile='first', failure_review=evidence)
        self.assertEqual(len(fixture.calls), 2)

    def test_recovery_total_call_time_and_token_budgets(self):
        fixture, engine, state = self.failing(max_calls=1)
        state = engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, capability=True))
        self.assertEqual(state['status'], 'budget_exhausted')
        self.assertEqual(len(fixture.calls), 1)
        fixture.status = 'completed'
        state = engine.resume(write=True, max_calls=2)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['controller']['recovery_counts']['escalations'], 1)
        with self.assertRaisesRegex(c.ContractError, 'unknown'):
            recovery.token_gate([codex.attempt('retry', 'model')], 100)
        with self.assertRaisesRegex(c.ContractError, 'exhausted'):
            recovery.token_gate(state['attempts'], 100)
        recovery.token_gate(state['attempts'], 181)  # 160 input + 20 output; cached subset not added.

    def test_recovery_confirmed_replan_preserves_completed_work_requires_acceptance(self):
        fixture = Fixture(self.project, [task('a'), task('b', ['a'])]); engine = fixture.engine()
        original = fixture.backend
        def fail_b(*args):
            fixture.status = 'unresolved' if '"id":"b"' in args[3] else 'completed'
            return original(*args)
        engine.backend = fail_b
        state = engine.start(goal(), write=True)
        self.assertEqual([t['status'] for t in state['tasks']], ['completed', 'failed'])
        completed = copy.deepcopy(state['tasks'][0])
        fixture.plan[1]['instructions'] += ' 확인된 인터페이스 변경 반영'
        engine.backend = fixture.backend; fixture.status = 'completed'
        state = engine.resume(write=True, reconcile='b', failure_review=self.evidence(state, 'plan', change='interface'))
        self.assertEqual(state['status'], 'approval_required')
        self.assertEqual(fixture.calls[-1]['phase'], 'replan')
        self.assertFalse(fixture.calls[-1]['write'])
        self.assertEqual(fixture.calls[-1]['model'], 'gpt-6.1-sol')
        with self.assertRaises(c.ContractError):
            engine.resume(write=True)
        count = len(fixture.calls)
        state = engine.resume(write=True, accept_replan=True)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['tasks'][0], completed)
        self.assertEqual(len(fixture.calls), count + 1)
        self.assertEqual(len(state['controller']['plan_history']), 1)
        self.assertEqual(state['controller']['recovery_counts']['replans'], 1)
        self.assertEqual(fixture.calls[-1]['model'], 'gpt-6-luna')

    def test_recovery_replan_cannot_drop_risks_completed_work_or_authorization(self):
        fixture, engine, state = self.failing(mode='project')
        for mutate in ('drop_risk', 'add_task', 'approval'):
            proposal = copy.deepcopy(fixture.plan)
            if mutate == 'drop_risk': proposal[0]['selection_context']['risks'] = []
            if mutate == 'add_task': proposal.append(task('new'))
            if mutate == 'approval': proposal[0]['approval_required'] = True
            with self.assertRaises(c.ContractError):
                recovery.reconcile_plan(state, proposal)

    def test_recovery_approval_is_not_bypassed_by_resume(self):
        fixture = Fixture(self.project, [task('guarded', approval=True)], status='unresolved')
        engine = fixture.engine(); state = engine.start(goal(), write=True)
        state = engine.resume(write=True, approve='guarded')
        state['controller']['approved'] = []  # Simulate approval revoked after inspecting new action.
        engine.save(state)
        state = engine.resume(write=True, reconcile='guarded', failure_review=self.evidence(state, capability=True))
        self.assertEqual(state['status'], 'approval_required')
        self.assertEqual(len(fixture.calls), 2)
        fixture.status = 'completed'
        state = engine.resume(write=True, approve='guarded')
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(fixture.calls[-1]['model'], 'gpt-6.1-sol')

    def test_recovery_invalid_sequence_rejected(self):
        value = copy.deepcopy(recovery.DEFAULT)
        value['sequence']['main'] = 'worker'
        with self.assertRaises(c.ContractError): recovery.policy(value)

    def test_recovery_environment_failure_action_and_same_model_manual_retry(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        def unavailable(*args):
            result = backend_response(args[1], args[-1], outcome(), failed=True)
            result.update(failure_kind='environment', error='executable unavailable')
            return result
        engine.backend = unavailable
        state = engine.start(goal(), mode='quick', write=True)
        self.assertEqual(state['controller']['records'][-1]['error_kind'], 'environment')
        self.assertIn('action:', state['controller']['records'][-1]['error'])
        engine.backend = fixture.backend
        state = engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, 'environment'))
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['attempts'][-1]['requested_model'], 'gpt-6-luna')
        self.assertEqual(state['controller']['recovery_counts']['escalations'], 0)

    def test_recovery_time_exhaustion_defers_pending_escalation(self):
        fixture, engine, state = self.failing()
        state['controller']['elapsed_seconds'] = state['controller']['max_seconds']
        engine.save(state)
        state = engine.resume(write=True, reconcile='request', failure_review=self.evidence(state, capability=True))
        self.assertEqual(state['status'], 'budget_exhausted')
        self.assertEqual(len(fixture.calls), 1)
        self.assertEqual(state['controller']['recovery_counts']['escalations'], 0)
        fixture.status = 'completed'
        state = engine.resume(write=True, max_seconds=7200)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(fixture.calls[-1]['model'], 'gpt-6.1-sol')

    def test_recovery_finite_token_budget_stops_unknown_and_overrun(self):
        fixture = Fixture(self.project); engine = fixture.engine()
        def unknown(*args):
            result = fixture.backend(*args)
            result['usage']['output_tokens'] = None
            return result
        engine.backend = unknown
        state = engine.start(goal(), write=True)
        self.assertEqual(state['status'], 'stopped')
        self.assertIn('token usage unknown', state['controller']['records'][-1]['error'])
        self.assertEqual(len(fixture.calls), 1)  # Unknown planning usage cannot admit implementation.
        self.assertIsNone(state['attempts'][0]['output_tokens'])
        other = self.project/'other'; other.mkdir(); (other/'.ai').mkdir()
        for name in ('models.yaml', 'routing.yaml', 'verification.yaml'):
            (other/'.ai'/name).write_bytes((self.project/'.ai'/name).read_bytes())
        second = Fixture(other); state = second.engine().start(goal(), mode='quick', write=True, max_tokens=50)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(state['tasks'][0]['status'], 'failed')
        self.assertIn('token budget exhausted/exceeded', state['controller']['records'][-1]['error'])

    def test_recovery_replan_limit_and_completed_definition_are_immutable(self):
        fixture, engine, state = self.failing(mode='project')
        state['controller']['recovery_counts']['replans'] = 1
        engine.save(state)
        with self.assertRaisesRegex(c.ContractError, 'replan limit'):
            engine.resume(write=True, reconcile='first', failure_review=self.evidence(state, 'plan', change='dependency'))
        state['tasks'][0]['status'] = 'completed'
        proposed = copy.deepcopy(fixture.plan); proposed[0]['instructions'] += ' rewrite'
        with self.assertRaisesRegex(c.ContractError, 'completed work'):
            recovery.reconcile_plan(state, proposed)

    def test_recovery_failed_replan_never_executes_stale_plan(self):
        fixture, engine, state = self.failing(mode='project')
        def interrupted(*args):
            raise KeyboardInterrupt()
        engine.backend = interrupted
        state = engine.resume(write=True, reconcile='first', failure_review=self.evidence(state, 'plan', change='design'))
        self.assertEqual(state['tasks'][0]['status'], 'interrupted')
        engine.backend = fixture.backend
        with self.assertRaisesRegex(c.ContractError, 'stale plan'):
            engine.resume(write=True, reconcile='first')
        with self.assertRaisesRegex(c.ContractError, 'replan limit'):
            engine.resume(write=True, reconcile='first', failure_review=self.evidence(state, 'plan', change='design'))
        self.assertEqual(len(fixture.calls), 2)


class VerificationTests(unittest.TestCase):
    stamp = 'a' * 64
    commands = {'test': 'fixture-check', 'lint': None}

    def run_mock(self, result=None, error=None, deadline=None, relevance=None):
        with patch.object(verification.subprocess, 'run', return_value=result, side_effect=error) as run:
            checks = verification.run_checks(Path.cwd(), self.commands,
                deadline if deadline is not None else verification.time.monotonic() + 60,
                self.stamp, relevance=relevance)
        return checks, run

    def passing(self):
        checks, _ = self.run_mock(Mock(returncode=0, stdout='실제 subprocess fixture', stderr=''))
        return checks

    def proof(self):
        return dict(name='test', command='fixture-check', scope='task', state_sha256=self.stamp,
                    source='explicit_user_review', review_id='review-1', reason='명시적으로 검토된 관련 없는 검사')

    def test_subprocess_success_nonzero_timeout_launch_failure_and_budget(self):
        checks = self.passing()
        self.assertTrue(verification.satisfied(checks, self.stamp))
        self.assertEqual(checks[1]['status'], 'unset')
        checks, _ = self.run_mock(Mock(returncode=23, stdout='', stderr='failed'))
        self.assertEqual(checks[0]['exit_code'], 23)
        self.assertFalse(verification.satisfied(checks, self.stamp))
        checks, _ = self.run_mock(error=verification.subprocess.TimeoutExpired('fixture', 1))
        self.assertTrue(checks[0]['executed']); self.assertIsNone(checks[0]['exit_code'])
        self.assertIn('timed out', checks[0]['reason'])
        checks, _ = self.run_mock(error=OSError('unavailable shell'))
        self.assertFalse(checks[0]['executed']); self.assertEqual(checks[0]['status'], 'required')
        self.assertIn('could not start', checks[0]['reason'])
        checks, run = self.run_mock(deadline=0)
        run.assert_not_called()
        self.assertEqual(checks[0]['status'], 'required')
        self.assertIn('budget exhausted', checks[0]['reason'])

    def test_uncertain_relevance_runs_full_configured_commands(self):
        checks, run = self.run_mock(Mock(returncode=0, stdout='', stderr=''))
        run.assert_called_once()
        verification.validate_results(checks, self.commands, 'task')
        args = run.call_args.args[0]
        self.assertIn('fixture-check', args[-1])
        self.assertFalse(run.call_args.kwargs['shell'])
        if verification.os.name == 'nt':
            self.assertIn('$global:LASTEXITCODE', args[-1])
            self.assertIn('exit $global:LASTEXITCODE', args[-1])

    def test_irrelevant_skip_requires_review_and_is_never_passed(self):
        proof = self.proof()
        checks, run = self.run_mock(relevance={'test': proof})
        run.assert_not_called()
        self.assertEqual(checks[0]['status'], 'irrelevant_skipped')
        verification.validate_results(checks, self.commands, 'task', {'test': proof})
        with self.assertRaises(c.ContractError):
            verification.validate_results(checks, self.commands, 'task')
        self.assertFalse(verification.satisfied(checks, self.stamp, {'test': proof}))
        for change in (dict(source='model_report'), dict(state_sha256='b'*64), dict(scope='final'), dict(command='changed')):
            with self.subTest(change=change):
                retained, run = self.run_mock(Mock(returncode=0, stdout='', stderr=''),
                                              relevance={'test': dict(proof, **change)})
                run.assert_called_once()
                self.assertEqual(retained[0]['status'], 'passed')
                self.assertIn('irrelevance uncertain', retained[0]['reason'])

    def test_mixed_skipped_and_passed_are_satisfied_only_with_proof(self):
        proof = self.proof()
        checks, _ = self.run_mock(relevance={'test': proof})
        passed = self.passing()[0]
        passed['name'] = 'acceptance'
        checks.append(passed)
        self.assertTrue(verification.satisfied(checks, self.stamp, {'test': proof}))
        self.assertFalse(verification.satisfied(checks, self.stamp))
        self.assertFalse(verification.satisfied(checks, 'b'*64, {'test': proof}))

    def test_model_claim_wrong_command_scope_and_missing_evidence_rejected(self):
        for mutate in (dict(producer='model_report'), dict(command='other'), dict(scope='final')):
            checks = self.passing(); checks[0].update(mutate)
            with self.assertRaises(c.ContractError):
                verification.validate_results(checks, self.commands, 'task')
        for checks in ([], self.passing()[:1]):
            with self.assertRaises(c.ContractError):
                verification.validate_results(checks, self.commands, 'task')

    def test_cache_requires_complete_tooling_and_same_scope_state_commands_environment(self):
        cache = verification.EvidenceCache(); checks = self.passing()
        tools = dict(complete=True, sha256='c'*64)
        for unknown in (None, {}, dict(complete=False)):
            cache.put(self.stamp, self.commands, 'task', unknown, checks)
            self.assertIsNone(cache.get(self.stamp, self.commands, 'task', unknown))
        cache.put(self.stamp, self.commands, 'task', tools, checks)
        hit = cache.get(self.stamp, self.commands, 'task', tools)
        self.assertEqual(hit, checks)
        hit[0]['reason'] = 'mutated copy'
        self.assertNotEqual(cache.get(self.stamp, self.commands, 'task', tools), hit)
        for stamp, commands, scope, identity in [
            ('b'*64, self.commands, 'task', tools),
            (self.stamp, dict(test='new-command', lint=None), 'task', tools),
            (self.stamp, self.commands, 'milestone', tools),
            (self.stamp, self.commands, 'final', tools),
            (self.stamp, self.commands, 'task', dict(complete=True, sha256='d'*64))]:
            self.assertIsNone(cache.get(stamp, commands, scope, identity))
        with patch.dict(verification.os.environ, {'REV_FIXTURE_TOOL_CHANGE': 'changed'}):
            self.assertIsNone(cache.get(self.stamp, self.commands, 'task', tools))

    def test_cache_never_keeps_failure_unset_or_unexecuted(self):
        tools = dict(complete=True, sha256='c'*64)
        for change in (dict(status='failed', exit_code=9), dict(status='required', executed=False, exit_code=None)):
            cache = verification.EvidenceCache(); checks = self.passing(); checks[0].update(change)
            cache.put(self.stamp, self.commands, 'task', tools, checks)
            self.assertFalse(cache.entries)
        self.assertNotEqual(verification.fingerprint({'file': 'x'}, {'config': 'x'}),
                            verification.fingerprint({'file': 'x'}, {'config': 'y'}))


if __name__ == '__main__':
    unittest.main()
