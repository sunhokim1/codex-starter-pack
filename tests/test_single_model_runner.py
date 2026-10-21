"""Observable invariants for the opt-in runner; no paid model calls."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]/"distribution/releases/0.3.3/universal-ai-starter/assets/runner"))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]/"distribution/releases/0.3.3/universal-ai-starter/scripts"))
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'distribution/releases/0.3.3/universal-ai-starter/assets/runner/run.py'
spec = importlib.util.spec_from_file_location('single_model_runner', MODULE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def events(*items):
    return '\n'.join(json.dumps(x) for x in items)


class RunnerTests(unittest.TestCase):
    def test_missing_completion_not_success(self):
        with self.assertRaises(ValueError):
            runner.parse_events(events({'type': 'item.completed', 'item':
                                        {'type': 'agent_message', 'text': 'ok'}}))

    def test_classifier_tool_use_stops(self):
        with self.assertRaises(ValueError):
            runner.parse_events(events({'type': 'item.started', 'item':
                                        {'type': 'command_execution'}}), classifier=True)

    def test_usage_is_not_double_counted(self):
        result = runner.parse_events(events(
            {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'done'}},
            {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 80}}))
        self.assertEqual(result['usage']['input_tokens'], 100)

    def execute_mock(self, choice, override=None,local=False,sev=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'task.txt').write_text('Do the requested task', encoding='utf-8')
            (root / 'models.yaml').write_text(
                'models:\n  worker:\n    model_id: test-luna\n  main:\n    model_id: test-sol\n',
                encoding='utf-8')
            (root / '.ai').mkdir()
            (root / '.ai/verification.yaml').write_text('commands:\n  test: fixture-check\n')
            args = SimpleNamespace(codex='codex', project=temp, task_file=root/'task.txt',
                                   context_file=None, models=root/'models.yaml', model=override,
                                   selection_timeout=90, execution_timeout=600, write=False,
                                   selector='sev' if sev else ('local' if local else 'codex'),
                                   sev_state='state.json',local_python='python',local_script='selector.py')
            results = [{'response': json.dumps(choice), 'usage': {}},
                       {'response': json.dumps({'outcome':'completed','summary':'fixture done','verification':[{'name':'test','command':'fixture-check','executed':True,'exit_code':0,'evidence':'fixture passed'}],'escalation':None}), 'usage': {}}]
            if override:
                results = results[1:]
            elif local or sev:
                results=results[1:]
            with patch('runtime_safety.private_permissions'), patch.object(runner.shutil, 'which', return_value='codex'), \
                 patch.object(runner, 'invoke', side_effect=results) as invoke, \
                 patch.object(runner.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(choice),stderr='')):
                report = runner.run(args)
                calls = invoke.call_args_list
            return report, calls

    def test_luna_selection_executes_once(self):
        report, calls = self.execute_mock({'role': 'worker', 'reason': 'clear local task'})
        self.assertEqual(report['status'], 'completed')
        self.assertEqual([c.args[1] for c in calls], ['test-luna', 'test-luna'])
        self.assertFalse(report['app_chat_model_changed'])

    def test_sol_selection_executes_once(self):
        report, calls = self.execute_mock({'role': 'main', 'reason': 'high impact'})
        self.assertEqual(report['status'], 'completed')
        self.assertEqual([c.args[1] for c in calls], ['test-luna', 'test-sol'])

    def test_user_override_skips_classifier(self):
        report, calls = self.execute_mock({}, override='main')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[1], 'test-sol')
        self.assertTrue(report['selection']['skipped'])

    def test_invalid_selection_does_not_execute(self):
        report, calls = self.execute_mock({'role': 'anything', 'reason': 'bad'})
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(calls), 1)
        self.assertIsNone(report['execution'])

    def test_local_selection_only_executes_one_codex_call(self):
        report,calls=self.execute_mock({'role':'worker','backend':'local','api_calls':0,'elapsed_seconds':0.01},local=True)
        self.assertEqual(report['status'],'completed')
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0].args[1],'test-luna')
        self.assertEqual(report['selection']['api_calls'],0)

    def test_invalid_local_selection_never_falls_back(self):
        report,calls=self.execute_mock({'role':'invalid','backend':'local','api_calls':0},local=True)
        self.assertEqual(report['status'],'failed')
        self.assertEqual(len(calls),0)

    def test_persistent_sev_executes_selected_sol_once(self):
        report,calls=self.execute_mock({'ok':True,'pid':123,'requests':2,
            'selection':{'role':'main','backend':'local','api_calls':0}},sev=True)
        self.assertEqual(report['status'],'completed')
        self.assertEqual([c.args[1] for c in calls],['test-sol'])
        self.assertEqual(report['selection']['service_pid'],123)

    def test_sev_failure_never_executes_or_uses_paid_classifier(self):
        report,calls=self.execute_mock({'ok':False,'error':'failed'},sev=True)
        self.assertEqual(report['status'],'failed')
        self.assertEqual(calls,[])

    def test_sev_user_override_skips_service(self):
        report,calls=self.execute_mock({},override='worker',sev=True)
        self.assertTrue(report['selection']['skipped'])
        self.assertEqual([c.args[1] for c in calls],['test-luna'])


if __name__ == '__main__':
    unittest.main()
