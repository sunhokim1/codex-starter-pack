"""Supervisor fixtures. These tests never constitute actual Rev inference."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ASSETS = Path(__file__).resolve().parents[1]/'assets'
sys.path.insert(0, str(ASSETS))
from rev import watchdog, smoke, service
from rev import hardware, loader
from rev.errors import RevError


class WatchdogTests(unittest.TestCase):
    def test_official_encoder_preflight_rejects_without_truncation_or_model_load(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        body = smoke.c.score_request(dict(task='한글', goal='보존', facts=[], constraints=['삭제 금지'],
            risks=['반환값 변경'], uncertainty=[], dependencies=[]), 'fixture')
        ids = list(range(700))
        encoder = Mock(return_value=(ids, [10, 20], ['worker', 'main']))
        official = SimpleNamespace(Scorer=SimpleNamespace(encode=encoder))
        with self.assertRaises(RevError) as caught:
            loader.preflight_rows(official, object(), body, 512)
        self.assertEqual(caught.exception.kind, 'oversize')
        self.assertIn('700', caught.exception.action)
        self.assertEqual(loader.preflight_rows(official, object(), body, 1024), [700])
        self.assertEqual(len(ids), 700)
        self.assertEqual(encoder.call_args.args[1], body['state'])

    def test_admission_can_only_reduce_watchdog_ceiling_and_still_requires_estimate(self):
        catalog = {'embed_tokens.weight': {'shape': [1, 1]}}
        report = dict(total_ram_bytes=16*1024**3, available_ram_bytes=4*1024**3)
        plan = hardware.execution_plan(report, catalog, process_budget_bytes=5*1024**3,
                                       budget_is_ceiling=True)
        self.assertLess(plan['process_budget_bytes'], plan['requested_process_budget_bytes'])
        self.assertLessEqual(plan['estimated_process_bytes'], plan['process_budget_bytes'])
        with self.assertRaises(RevError):
            hardware.execution_plan(dict(report, available_ram_bytes=2*1024**3), catalog,
                process_budget_bytes=5*1024**3, budget_is_ceiling=True)

    def sample(self):
        return dict(rss_bytes=20, private_bytes=30, peak_job_commit_bytes=40, available_ram_bytes=100,
                    processes=[dict(peak_rss_bytes=25, peak_commit_bytes=35)])

    def test_limits_unknown_monitor_deadline_and_os_peak_fail_closed(self):
        watchdog.check_sample(self.sample(), 50, 80, time.monotonic()+2)
        for key, value, kind in [('rss_bytes', 51, 'resource'), ('private_bytes', 51, 'resource'),
                                 ('peak_job_commit_bytes', 51, 'resource'),
                                 ('available_ram_bytes', 79, 'resource'), ('private_bytes', None, 'monitor')]:
            sample = self.sample(); sample[key] = value
            with self.assertRaises(RevError) as caught:
                watchdog.check_sample(sample, 50, 80, time.monotonic()+2)
            self.assertEqual(caught.exception.kind, kind)
        with self.assertRaises(RevError) as caught:
            watchdog.check_sample(self.sample(), 50, 80, time.monotonic()-1)
        self.assertEqual(caught.exception.kind, 'timeout')
        sample = self.sample(); sample['processes'][0]['peak_commit_bytes'] = 51
        with self.assertRaises(RevError):
            watchdog.check_sample(sample, 50, 80, time.monotonic()+2)

    def test_fake_score_cannot_be_reported_as_real_worker_evidence(self):
        with patch.object(smoke.c, 'validate_response'):
            for ping in ({}, {'warmed': True, 'ready': True, 'last_score': {'encoded_tokens': [3]}}):
                with self.assertRaises(RevError) as caught:
                    smoke.actual_evidence(ping, {'answers': {}}, {})
                self.assertEqual(caught.exception.kind, 'evidence')

    def test_worker_evidence_must_match_preflight_and_exact_request(self):
        # Synthetic metadata tests validation only; it is never saved as real evidence.
        request = {'fixture': '한글'}
        measurement = dict(evidence='actual-pinned-worker', encoded_tokens=[525],
            request_bytes=len(smoke.c.json_bytes(request)), score_seconds=1.25)
        ping = dict(inference_evidence='official-warmup-completed; authenticated-score-evidence-required',
            derived_manifest_sha256='fixture', preflight_encoded_tokens=[525], last_score=measurement)
        with patch.object(smoke.c, 'validate_response'):
            self.assertTrue(smoke.actual_evidence(ping, {}, request)['actual_inference'])
            for change in (dict(encoded_tokens=[512]), dict(request_bytes=1),
                           dict(score_seconds=float('nan')), dict(score_seconds=-1)):
                with self.assertRaises(RevError):
                    smoke.actual_evidence(dict(ping, last_score=dict(measurement, **change)), {}, request)

    def test_extended_deadlines_are_finite_and_validated_before_worker_spawn(self):
        for load, score in ((1801, 30), (600, 901), (float('inf'), 30), (600, float('nan'))):
            with patch.object(service.mp, 'get_context') as spawn:
                with self.assertRaises(RevError):
                    service.Worker({}, load, score)
                spawn.assert_not_called()

    def test_redirected_gateway_requires_job_membership_and_fresh_nonce(self):
        state = dict(pid=22, connection=dict(runtime_id='fresh'))
        membership = dict(processes=[dict(pid=11), dict(pid=22), dict(pid=33)])
        self.assertEqual(smoke.owned_gateway(state, 'fresh', membership), 22)
        for runtime, members in [('old', membership), ('fresh', dict(processes=[dict(pid=11)]))]:
            with self.assertRaises(RevError) as caught:
                smoke.owned_gateway(state, runtime, members)
            self.assertEqual(caught.exception.kind, 'identity')

    def test_bounded_serve_propagates_plan_and_deadlines(self):
        # Abort at constructor so no fake HTTP result can masquerade as a smoke.
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, REV_TEST_TOKEN='x'*40), \
                patch.object(service, 'Worker', side_effect=RuntimeError('fixture')) as worker:
            with self.assertRaises(RuntimeError):
                service.serve(Path(directory)/'state', 'REV_TEST_TOKEN', 'fixture', 'base', 'adapter', 'env',
                    'cpu', 'bf16', 1500, 600, memory_mode='bounded-cpu', row_token_budget=512,
                    offload_directory='derived', process_budget_bytes=3000, safety_margin_bytes=1000)
            arguments, load, score = worker.call_args.args
            self.assertEqual((load, score), (1500, 600))
            self.assertEqual(arguments['memory_mode'], 'bounded-cpu')
            self.assertEqual(arguments['process_budget_bytes'], 3000)

    def test_worker_score_metadata_is_separate_from_contract_response(self):
        from unittest.mock import Mock
        worker = service.Worker.__new__(service.Worker)
        worker.ready = True; worker.process = Mock(); worker.process.is_alive.return_value = True
        worker.pipe = Mock(); worker.score_timeout = 600; worker.info = {}
        expected = {'answers': {'fixture': True}}
        measurement = dict(encoded_tokens=[123], request_bytes=456, score_seconds=1.2,
                           evidence='actual-pinned-worker')
        with patch.object(worker, 'receive', return_value=dict(response=expected, measurement=measurement)):
            self.assertIs(worker.score({'fixture': True}), expected)
        self.assertEqual(worker.info['last_score'], measurement)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object contract')
    def test_real_job_commit_limit_rejects_allocation_between_samples(self):
        job = watchdog.OwnedJob(64*1024**2)
        child = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c',
            'import sys; sys.stdin.buffer.read(1)\n'
            'try:\n x=bytearray(128*1024**2); print("unexpected")\n'
            'except MemoryError:\n print("bounded-allocation-rejected")'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            job.assign(child)
            stdout, stderr = child.communicate(b'1', timeout=5)
            self.assertEqual(child.returncode, 0, stderr)
            self.assertEqual(stdout.strip(), b'bounded-allocation-rejected')
        finally:
            job.close()
            if child.poll() is None:
                child.kill(); child.wait(timeout=5)

    @unittest.skipUnless(os.name == 'nt', 'Windows Job Object contract')
    def test_real_owned_job_descendants_cleanup_and_unrelated_survival(self):
        job = watchdog.OwnedJob(256*1024**2)
        self.assertEqual(job.sample()['enforced_job_commit_limit_bytes'], 256*1024**2)
        unrelated = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', 'import time; time.sleep(20)'],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        child = subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c',
            'import sys,subprocess,time; sys.stdin.buffer.read(1); '
            'subprocess.Popen([sys.executable,"-I","-S","-B","-c","import time; time.sleep(20)"]); time.sleep(20)'],
            stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            job.assign(child)
            child.stdin.write(b'1'); child.stdin.close()
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                sample = job.sample()
                if len(sample['processes']) >= 2:
                    break
                time.sleep(.05)
            # Windows may also assign an owned console host to this job.
            self.assertGreaterEqual(len(sample['processes']), 2)
            self.assertNotIn(unrelated.pid, [row['pid'] for row in sample['processes']])
            self.assertGreater(sample['private_bytes'], 0)
            self.assertGreater(sample['peak_job_commit_bytes'], 0)
            job.terminate(); child.wait(timeout=5)
            deadline = time.monotonic()+5
            while job.sample()['processes'] and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertEqual(job.sample()['processes'], [])
            self.assertIsNone(unrelated.poll())
        finally:
            job.close()
            if child.poll() is None:
                child.kill(); child.wait(timeout=5)
            unrelated.terminate(); unrelated.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
