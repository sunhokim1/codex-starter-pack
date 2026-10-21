import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

BUNDLE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rev_040_contracts', BUNDLE / 'assets/rev/contracts.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
HASH = 'a' * 64


def context():
    return dict(task='한글 문서 편집', goal='모든 요구 보존', facts=['기존 사실'],
                risks=['결제', '권한', '데이터 변경', '원인 불명 버그'],
                constraints=['승인 전 실행 금지'], uncertainty=['원인 미확인'],
                dependencies=[{'id': 'direct', 'interface': 'summary only', 'changed_files': [], 'checks': []}])


def state():
    return dict(version=4, project='fixture', configuration={'config': HASH},
                models=dict(planning_model='gpt-6.1-sol', execution_model=None),
                tasks=[dict(id='done', status='completed', depends_on=[], execution_model=None),
                       dict(id='next', status='pending', depends_on=['done'], execution_model=None)],
                attempts=[], status='pending')


def evidence():
    return dict(name='test', command='python -m unittest', scope='task', status='passed',
                producer='controller_subprocess', state_sha256=HASH, executed=True, exit_code=0,
                reason='fixture subprocess result')


class RevContractTests(unittest.TestCase):
    def test_official_provenance_and_lock(self):
        lock = json.loads((BUNDLE / 'contracts/upstream.lock.json').read_text())
        c.validate_lock(lock)
        self.assertEqual(lock['base']['revision'], '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a')
        self.assertEqual(lock['adapter']['artifacts']['checkpoint.pt'],
                         '6417fd6b8f41449730957f827b8d009ce69d5feadaddd41951a3dff8ad772b96')
        with self.assertRaises(c.ContractError):
            c.require_installable(lock)
        for change in (lambda x: x['source'].update(revision='main'),
                       lambda x: x['adapter']['artifacts'].update({'../escape': HASH}),
                       lambda x: x['dependencies']['accelerate'].update(version='invented'),
                       lambda x: x.update(unrecognized=True)):
            malformed = copy.deepcopy(lock); change(malformed)
            with self.assertRaises(c.ContractError):
                c.validate_lock(malformed)
        index = json.loads((BUNDLE / 'contracts/provenance/index.json').read_text())
        c.verify_artifacts(BUNDLE / 'contracts/provenance', {k: v['sha256'] for k, v in index.items()})
        examples = json.loads((BUNDLE / 'contracts/examples.json').read_text())
        for name, validator in (('connection', c.validate_connection), ('models', c.validate_models),
                                ('state', c.validate_state), ('usage', c.validate_usage),
                                ('evidence', c.validate_evidence)):
            validator(examples[name])
        release = json.loads((BUNDLE / 'release.json').read_text())
        self.assertEqual(release['version'], '0.4.0')
        files = {str(p.relative_to(BUNDLE)).replace('\\', '/') for p in BUNDLE.rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.name != 'release.json'}
        self.assertEqual(set(release['sha256']), {'universal-ai-starter/' + p for p in files})
        for name, checksum in release['sha256'].items():
            self.assertEqual(hashlib.sha256((BUNDLE / name.removeprefix('universal-ai-starter/')).read_bytes()).hexdigest(), checksum)

    def test_artifact_integrity_before_any_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.pt'; path.write_bytes(b'fixture only')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(c.verify_artifacts(directory, {'checkpoint.pt': expected})['checkpoint.pt'], path.resolve())
            path.write_bytes(b'corrupted')
            for manifest in ({'checkpoint.pt': expected}, {'../checkpoint.pt': expected}, {'C:/escape': expected}, {}):
                with self.assertRaises(c.ContractError):
                    c.verify_artifacts(directory, manifest)

    def test_korean_long_document_context_is_lossless(self):
        original = context(); original['task'] += '\n문서 원문' * 2000
        request = c.score_request(original, '적합한 구현 모델을 선택하세요')
        self.assertEqual(request['state'], original)
        original['risks'].append('new risk')
        self.assertNotIn('new risk', request['state']['risks'])
        self.assertEqual(set(request), {'state', 'questions'})
        self.assertEqual(set(request['questions'][0]['criteria']), {'worker', 'main'})
        original['task'] = '한' * c.MAX_REQUEST_BYTES
        with self.assertRaisesRegex(c.ContractError, 'too large'):
            c.score_request(original, 'choose')
        for key in context():
            incomplete = context(); del incomplete[key]
            with self.assertRaises(c.ContractError):
                c.score_request(incomplete, 'choose')

    def test_official_response_conversion(self):
        request = c.score_request(context(), 'choose')
        response = dict(answers={'execution_model': dict(choice='main', probabilities=dict(worker=.2, main=.8))},
                        server_seconds=.01, path='rows', generated_tokens=0,
                        rows=[dict(gpu_seconds=.01, batch_rows=1, batch_padded_tokens=256, queued_seconds=0.)])
        self.assertIs(c.validate_response(request, response), response)
        for change in (lambda x: x['answers']['execution_model'].update(choice='worker'),
                       lambda x: x['answers']['execution_model']['probabilities'].update(main=float('nan')),
                       lambda x: x.update(generated_tokens=1), lambda x: x.update(rows=[]),
                       lambda x: x.update(answers={}), lambda x: x.update(server_seconds=True)):
            broken = copy.deepcopy(response); change(broken)
            with self.assertRaises(c.ContractError):
                c.validate_response(request, broken)
        # Official state accepts plain strings and JSON, without a text-generation envelope.
        c.validate_request(dict(state='문서 원문', questions=request['questions']))
        broken = copy.deepcopy(request); broken['questions'] *= 2
        with self.assertRaises(c.ContractError):
            c.validate_request(broken)

    def test_loopback_connection_has_only_secret_reference(self):
        connection = dict(contract_version=1, runtime_version='0.4.0', runtime_id='isolated-040',
                          endpoint='http://127.0.0.1:8000', token_env='REV_AUTH_TOKEN', lock_sha256=HASH)
        c.validate_connection(connection)
        for endpoint in ('http://0.0.0.0:8000', 'http://localhost:8000', 'http://secret@127.0.0.1:8000',
                         'http://127.0.0.1:8000?token=secret', 'http://127.0.0.1:bad', 'http://example.com:8000'):
            with self.assertRaises(c.ContractError):
                c.validate_connection(dict(connection, endpoint=endpoint))
        with self.assertRaises(c.ContractError):
            c.validate_connection(dict(connection, token='secret'))

    def test_planning_never_pins_execution(self):
        models = state()['models']
        self.assertIsNone(c.execution_override(models))
        self.assertEqual(c.execution_override(models, 'worker'), 'worker')
        models['execution_model'] = 'main'
        self.assertEqual(c.execution_override(models), 'main')
        self.assertEqual(c.execution_override(models, 'worker'), 'worker')
        with self.assertRaises(c.ContractError):
            c.execution_override(models, 'auto')

    def test_legacy_state_remains_readable_and_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            for old in (dict(version=3, model='main', status='completed', tasks=[{'id': 'done', 'status': 'completed'}]),
                        dict(version=999, status='unknown'), dict(version=4, status='malformed')):
                before = json.dumps(old).encode(); path.write_bytes(before)
                report = c.read_status(path)
                self.assertFalse(report['compatible']); self.assertFalse(report['resume_allowed'])
                self.assertEqual(path.read_bytes(), before)
                with self.assertRaises(c.ContractError):
                    c.resumable_tasks(old, 'fixture', {'config': HASH})

    def test_no_completed_replay_or_uncertain_resume(self):
        current = state(); original = copy.deepcopy(current)
        self.assertEqual([t['id'] for t in c.resumable_tasks(current, 'fixture', {'config': HASH})], ['next'])
        self.assertEqual(current, original)
        for status in ('running', 'failed', 'interrupted', 'approval_required'):
            broken = state(); broken['tasks'][1]['status'] = status
            with self.assertRaises(c.ContractError):
                c.resumable_tasks(broken, 'fixture', {'config': HASH})
        with self.assertRaises(c.ContractError):
            c.resumable_tasks(current, 'fixture', {'config': 'b' * 64})
        with self.assertRaises(c.ContractError):
            c.resumable_tasks(current, 'other project', {'config': HASH})
        for change in (lambda x: x['tasks'][0].update(depends_on=['next']),
                       lambda x: x['tasks'][1].update(id='done'), lambda x: x.update(version=True)):
            broken = state(); change(broken)
            with self.assertRaises(c.ContractError):
                c.validate_state(broken)

    def test_unknown_failed_call_usage_is_not_zero(self):
        attempt = dict(phase='retry', status='failed', requested_model='gpt-6-luna', actual_model=None,
                       elapsed_seconds=1.2, input_tokens=None, cached_input_tokens=None,
                       output_tokens=None, cli_invocations=1, backend_requests=None)
        c.validate_usage(attempt)
        self.assertIsNone(attempt['input_tokens']); self.assertIsNone(attempt['actual_model'])
        for change in (dict(input_tokens=-1), dict(elapsed_seconds=float('inf')),
                       dict(input_tokens=1, cached_input_tokens=2), dict(cli_invocations=True)):
            with self.assertRaises(c.ContractError):
                c.validate_usage(dict(attempt, **change))

    def test_only_identical_controller_evidence_satisfies(self):
        check = evidence()
        self.assertTrue(c.evidence_satisfies(check, HASH))
        self.assertFalse(c.evidence_satisfies(check, 'b' * 64))
        self.assertFalse(c.evidence_satisfies(dict(check, producer='model_report'), HASH))
        c.validate_evidence(dict(check, status='unset', command=None, state_sha256=None, executed=False, exit_code=None))
        c.validate_evidence(dict(check, status='irrelevant_skipped', executed=False, exit_code=None))
        with self.assertRaises(c.ContractError):
            c.validate_evidence(dict(check, executed=False))


if __name__ == '__main__':
    unittest.main()
