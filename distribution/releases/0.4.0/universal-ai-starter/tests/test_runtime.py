"""Offline protocol fixtures, not inference or comparative model quality evaluation."""
import copy
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import MagicMock, Mock, patch

BUNDLE = Path(__file__).resolve().parents[1]
PACKAGE = '_rev040_runtime_fixture'
if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(PACKAGE, BUNDLE / 'assets/rev/__init__.py',
                                                submodule_search_locations=[str(BUNDLE / 'assets/rev')])
    module = importlib.util.module_from_spec(spec); sys.modules[PACKAGE] = module; spec.loader.exec_module(module)
from importlib import import_module
c = import_module(PACKAGE + '.contracts')
selector = import_module(PACKAGE + '.selector')
service = import_module(PACKAGE + '.service')
hardware = import_module(PACKAGE + '.hardware')
loader = import_module(PACKAGE + '.loader')
offload = import_module(PACKAGE + '.offload')
RevError = import_module(PACKAGE + '.errors').RevError
MODELS = dict(planning_model='gpt-6.1-sol', execution_model=None)
TOKEN = 'offline_fixture_token_' + 'x' * 40


def context():
    return dict(task='한글 문서 편집: 원문을 보존하고 오탈자만 고친다', goal='모든 필수 제약 보존',
                facts=['기존 프로젝트 설정 유지'], risks=['권한 변경', '결제', '데이터 삭제', '원인 불명 버그'],
                constraints=['승인 전 실행 금지', '외부 전송 금지'], uncertainty=['오류 원인 미확인'],
                dependencies=[dict(id='direct', summary='직접 인터페이스', changed_files=['a.docx'], checks=['fixture'])])


def response(body, worker=0.91):
    return dict(answers={body['questions'][0]['id']: dict(choice='worker' if worker >= .5 else 'main',
                    probabilities=dict(worker=worker, main=1-worker))}, server_seconds=.01, path='rows',
                rows=[dict(gpu_seconds=.01, batch_rows=1, batch_padded_tokens=160, queued_seconds=0)], generated_tokens=0)


def ready_info():
    lock = json.loads((BUNDLE / 'contracts/upstream.lock.json').read_text())
    return dict(model=lock['base']['repo'], revision=lock['base']['revision'],
                adapter_revision=lock['adapter']['revision'], checkpoint_sha256=lock['adapter']['artifacts']['checkpoint.pt'],
                temperature=1.96, state_format='raw', device='cuda:0', dtype='bf16', ready=True, warmed=True,
                max_row_tokens=16384)


class FakeWorker:
    def __init__(self):
        self.ready = True; self.info = ready_info(); self.calls = []

    def score(self, body):
        self.calls.append(copy.deepcopy(body))
        return response(body)

    def is_ready(self):
        return self.ready


class ServerFixture:
    def __enter__(self):
        self.env = patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN); self.env.start()
        self.worker = FakeWorker()
        self.server = service.make_server(self.worker, TOKEN, 'fixture_runtime', 'REV_AUTH_TOKEN')
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.client = selector.Client(self.server.connection_info, timeout=2)
        return self

    def __exit__(self, *args):
        self.server.shutdown(); self.thread.join(timeout=2); self.server.server_close(); self.env.stop()


class RuntimeFixtures(unittest.TestCase):
    def test_vendored_records_are_verified_payload_not_installation_manifests(self):
        import base64
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            site = prefix / ('Lib/site-packages' if os.name == 'nt' else
                             'lib/python%d.%d/site-packages' % sys.version_info[:2])
            primary = 'fixture-1.dist-info/RECORD'
            payload = {'fixture/_vendor/vendor-1.dist-info/RECORD': b'vendored record',
                       'fixture/_vendor/code.py': b'value = 1\n'}
            rows = []
            for name, raw in payload.items():
                path = site / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
                digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
                rows.append('%s,sha256=%s,%d\n' % (name, digest, len(raw)))
            raw = (''.join(rows) + primary + ',,\n').encode()
            record = site / primary; record.parent.mkdir(parents=True); record.write_bytes(raw)
            wheel = prefix / 'fixture.whl'; wheel.write_bytes(b'explicit offline fixture')
            receipt = prefix / 'environment.json'
            receipt.write_text(json.dumps(dict(schema=1, resolved=True, distributions={
                'fixture': dict(version='1', wheel=str(wheel), wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
                                record_sha256=hashlib.sha256(raw).hexdigest())})))
            dist = SimpleNamespace(metadata={'Name': 'fixture'}, version='1',
                                   files=[*payload, primary], locate_file=lambda p: site / p)
            flags = SimpleNamespace(isolated=True, no_site=True, dont_write_bytecode=True)
            with patch.object(loader, 'isolated_prefix', return_value=prefix), patch.object(loader.sys, 'flags', flags), \
                 patch.object(loader.sys, 'path', list(sys.path)), \
                 patch.object(loader.importlib.metadata, 'distributions', return_value=[dist]):
                loader.verify_environment(receipt, {'dependencies': {}})
                (site / 'fixture/_vendor/code.py').write_bytes(b'value = 2\n')
                with self.assertRaisesRegex(RevError, 'hash mismatch'):
                    loader.verify_environment(receipt, {'dependencies': {}})

    def closing_response(self, body, declared_length):
        # Real HTTPResponse.read1 closes its file on the final nonempty
        # Content-Length read. Model the OS socket's final reference closing
        # too, as observed in the Windows loopback lifecycle fixtures.
        channel = Mock()
        channel.closed = False

        class ClosingFile(io.BytesIO):
            def close(self):
                channel.closed = True
                super().close()

        def settimeout(value):
            if channel.closed:
                raise OSError('socket already closed')

        channel.settimeout.side_effect = settimeout
        length = b'' if declared_length is None else b'Content-Length: ' + str(declared_length).encode() + b'\r\n'
        channel.makefile.return_value = ClosingFile(b'HTTP/1.0 200 OK\r\n' + length + b'\r\n' + body)
        reply = http.client.HTTPResponse(channel)
        reply.begin()
        return channel, reply

    def test_client_final_nonempty_read_closes_socket_without_another_timeout(self):
        raw = json.dumps({'document': 'x' * 20000}).encode()
        channel, reply = self.closing_response(raw, len(raw))
        connection = service.connection_for('http://127.0.0.1:12345', 'test', 'REV_AUTH_TOKEN')
        with patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(selector.http.client, 'HTTPConnection') as transport:
            transport.return_value.sock = channel
            transport.return_value.getresponse.return_value = reply
            self.assertEqual(selector.Client(connection).call('/ping'), json.loads(raw))
        self.assertTrue(channel.closed)
        self.assertTrue(reply.isclosed())
        self.assertEqual(reply.length, 0)
        # One timeout for headers and three body reads, no empty fourth read.
        self.assertEqual(channel.settimeout.call_count, 4)
        transport.return_value.close.assert_called_once()

    def test_client_rejects_truncated_length_even_when_received_json_is_valid(self):
        raw = b'{"ready":true}'
        channel, reply = self.closing_response(raw, len(raw) + 10)
        connection = service.connection_for('http://127.0.0.1:12345', 'test', 'REV_AUTH_TOKEN')
        with patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(selector.http.client, 'HTTPConnection') as transport:
            transport.return_value.sock = channel
            transport.return_value.getresponse.return_value = reply
            with self.assertRaises(RevError) as caught:
                selector.Client(connection).call('/ping')
        self.assertEqual(caught.exception.kind, 'protocol')
        self.assertTrue(reply.isclosed())
        transport.return_value.close.assert_called_once()

    def test_client_close_delimited_response_stops_after_eof(self):
        channel, reply = self.closing_response(b'{"ready":true}', None)
        connection = service.connection_for('http://127.0.0.1:12345', 'test', 'REV_AUTH_TOKEN')
        with patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(selector.http.client, 'HTTPConnection') as transport:
            transport.return_value.sock = channel
            transport.return_value.getresponse.return_value = reply
            self.assertEqual(selector.Client(connection).call('/ping'), {'ready': True})
        self.assertTrue(channel.closed)
        transport.return_value.close.assert_called_once()

    def test_client_stream_limit_and_absolute_deadline_survive_final_read(self):
        connection = service.connection_for('http://127.0.0.1:12345', 'test', 'REV_AUTH_TOKEN')
        for raw, times, kind in ((b' ' * (c.MAX_REQUEST_BYTES + 1), [0] * 100, 'protocol'),
                                 (b'{}', [0, 0, 0, 31], 'timeout')):
            channel, reply = self.closing_response(raw, len(raw))
            with patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(selector.http.client, 'HTTPConnection') as transport, patch.object(selector.time, 'monotonic', side_effect=times):
                transport.return_value.sock = channel
                transport.return_value.getresponse.return_value = reply
                with self.assertRaises(RevError) as caught:
                    selector.Client(connection).call('/ping')
                self.assertEqual(caught.exception.kind, kind)
                transport.return_value.close.assert_called_once()

    def test_official_http_request_and_response_korean_risks(self):
        with ServerFixture() as fixture:
            original = context()
            selected = selector.select(original, MODELS, client_factory=lambda: fixture.client)
            self.assertEqual(selected['model'], 'worker')
            self.assertEqual(selected['probability_semantics'], 'option_probabilities_not_coding_success')
            self.assertIsNone(selected['actual_model'])
            self.assertEqual(fixture.worker.calls[0]['state'], original)
            self.assertEqual(set(fixture.worker.calls[0]), {'state', 'questions'})
            self.assertEqual(set(fixture.worker.calls[0]['questions'][0]['criteria']), {'worker', 'main'})

    def test_global_and_task_override_do_not_construct_rev_or_inspect_context(self):
        factory = Mock(side_effect=AssertionError('Rev must be bypassed'))
        for global_model, task_model, expected in ((None, 'worker', 'worker'), ('main', None, 'main'), ('main', 'worker', 'worker')):
            result = selector.select(None, dict(MODELS, execution_model=global_model), task_model, factory)
            self.assertEqual(result['model'], expected)
            self.assertEqual(result['source'], 'explicit_override')
        factory.assert_not_called()

    def test_planning_sol_does_not_pin_implementation(self):
        client = Mock(); client.call.side_effect = lambda path, body: response(body)
        result = selector.select(context(), MODELS, client_factory=lambda: client)
        self.assertEqual(result['requested_model'], 'gpt-6-luna')
        client.ready.assert_called_once()

    def test_long_document_not_silently_truncated(self):
        task = context(); task['task'] += '긴 원문\n' * 5000
        body = c.score_request(task, selector.INSTRUCTIONS)
        self.assertEqual(body['state'], task)
        task['task'] *= 50
        factory = Mock()
        with self.assertRaises(RevError) as caught:
            selector.select(task, MODELS, client_factory=factory)
        self.assertEqual(caught.exception.kind, 'oversize')
        factory.assert_not_called()

    def test_actual_official_encode_layout_and_row_limit(self):
        lock, metadata, source = loader.locked_provenance()
        official = types.ModuleType('fixture_official')
        exec(compile(source, 'verified_fixture_source', 'exec'), official.__dict__)
        scorer = official.Scorer.__new__(official.Scorer)
        scorer.state_format = 'raw'
        scorer.tok = Mock()
        scorer.tok.encode.side_effect = lambda s, **kw: list(s.encode('utf-8'))
        q = {'id': 'q', 'instructions': '한글 질문', 'criteria': {'worker': '가', 'main': '나'}}
        ids, positions, keys = scorer.encode('문서 원문', q)
        self.assertEqual(bytes(ids).decode(), 'State:\n문서 원문\nQuestion: 한글 질문\nOptions:\nworker: 가\nmain: 나\nDecision:')
        self.assertEqual(keys, ['worker', 'main']); self.assertEqual(len(positions), 2)
        body = c.score_request(context(), selector.INSTRUCTIONS)
        scorer.encode = Mock(return_value=([0] * 16384, [1, 2], ['worker', 'main']))
        loader.check_rows(scorer, body)
        scorer.encode.return_value = ([0] * 16385, [1, 2], ['worker', 'main'])
        with self.assertRaises(RevError) as caught:
            loader.check_rows(scorer, body)
        self.assertEqual(caught.exception.kind, 'oversize')

    def test_malformed_probability_option_choice_and_rows_fail_closed(self):
        body = c.score_request(context(), selector.INSTRUCTIONS)
        for mutate in (lambda r: r['answers']['execution_model'].update(choice='unknown'),
                       lambda r: r['answers']['execution_model']['probabilities'].update(worker=float('nan')),
                       lambda r: r['answers']['execution_model']['probabilities'].update(main=.8),
                       lambda r: r.update(answers={'wrong_id': {}}),
                       lambda r: r['rows'][0].update(batch_padded_tokens=20000),
                       lambda r: r.update(generated_tokens=1)):
            bad = response(body); mutate(bad)
            client = Mock(); client.call.return_value = bad
            with self.assertRaises(RevError):
                selector.select(context(), MODELS, client_factory=lambda: client)

    def test_uncertainty_abstains_without_automatic_sol_fallback(self):
        client = Mock(); client.call.side_effect = lambda path, body: response(body, .65)
        with self.assertRaises(RevError) as caught:
            selector.select(context(), MODELS, client_factory=lambda: client)
        self.assertEqual(caught.exception.kind, 'abstention')
        self.assertEqual(client.call.call_count, 1)

    def test_auth_remote_origin_and_public_bind_rejected(self):
        connection = service.connection_for('http://127.0.0.1:12345', 'test', 'REV_AUTH_TOKEN')
        headers = {'Authorization': 'Bearer ' + TOKEN, 'X-Rev-Runtime': 'test', 'X-Rev-Lock': connection['lock_sha256']}
        service.authenticate('127.0.0.1', headers, TOKEN, connection)
        for peer, patch_headers in (('192.168.1.2', {}), ('127.0.0.1', {'Origin': 'https://example.org'}),
                                    ('127.0.0.1', {'Authorization': 'Bearer wrong'}), ('127.0.0.1', {'X-Rev-Runtime': 'other'})):
            with self.assertRaises(RevError):
                service.authenticate(peer, dict(headers, **patch_headers), TOKEN, connection)
        with self.assertRaises(RevError):
            service.make_server(FakeWorker(), TOKEN, 'test', 'REV_AUTH_TOKEN', host='0.0.0.0')

    def test_actual_http_unauthenticated_and_oversize_rejection(self):
        with ServerFixture() as fixture:
            transport = http.client.HTTPConnection('127.0.0.1', fixture.server.server_port, timeout=2)
            transport.request('POST', '/ping', body=b'{}', headers={'Content-Type': 'application/json'})
            self.assertEqual(transport.getresponse().status, 403); transport.close()
            connection = fixture.server.connection_info
            transport = http.client.HTTPConnection('127.0.0.1', fixture.server.server_port, timeout=2)
            transport.request('POST', '/score', body=b'{}', headers={'Authorization': 'Bearer ' + TOKEN,
                 'X-Rev-Runtime': connection['runtime_id'], 'X-Rev-Lock': connection['lock_sha256'],
                 'Content-Type': 'application/json', 'Content-Length': str(c.MAX_REQUEST_BYTES+1)})
            self.assertEqual(transport.getresponse().status, 413); transport.close()
            self.assertEqual(fixture.worker.calls, [])

    def test_lifecycle_reuses_warmed_model_and_authenticated_stop(self):
        with ServerFixture() as fixture, tempfile.TemporaryDirectory() as directory:
            state = Path(directory)/'state.json'
            service.write_exclusive(state, dict(connection=fixture.server.connection_info, pid=os.getpid()))
            with patch.object(service.subprocess, 'Popen', side_effect=AssertionError('must reuse')):
                for _ in range(2):
                    info = service.ensure_started(state, 'unused', 'unused', 'unused', 'unused')
                    self.assertTrue(info['warmed'])
            self.assertEqual(service.stop(state)['pid'], os.getpid())
            self.assertTrue(fixture.server.stopping)

    def test_dead_worker_still_supports_authenticated_stop(self):
        with ServerFixture() as fixture, tempfile.TemporaryDirectory() as directory:
            fixture.worker.ready = False
            state = Path(directory)/'state.json'
            service.write_exclusive(state, dict(connection=fixture.server.connection_info, pid=os.getpid()))
            with self.assertRaises(RevError):
                service.status(state)
            self.assertTrue(service.stop(state)['stopped'])

    def test_no_reuse_from_health_or_wrong_pid_or_stale_state(self):
        with ServerFixture() as fixture, tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state.json'
            service.write_exclusive(path, dict(connection=fixture.server.connection_info, pid=os.getpid()+1))
            before = path.read_bytes()
            with self.assertRaises(RevError):
                service.ensure_started(path, 'unused', 'unused', 'unused', 'unused')
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(RevError):
                service.stop(path)
            with self.assertRaises(RevError):
                selector.validate_ready({'ok': True}, fixture.server.connection_info)

    def test_state_is_exclusive_and_contains_no_token(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'state.json'; service.write_exclusive(path, {'pid': 1})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                service.write_exclusive(path, {'pid': 2})
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn(TOKEN.encode(), before)

    def test_windows_intel_low_memory_blocks_before_artifact_or_model_access(self):
        report = dict(os='Windows', machine='AMD64', total_ram_bytes=int(15.7*hardware.GIB),
                      available_ram_bytes=int(1.9*hardware.GIB), cuda_driver_observed=False, nvidia=[])
        self.assertEqual(hardware.installation_modes(report)['modes'], [])
        with patch.object(loader, 'diagnose', return_value=report), patch.object(loader, 'locked_provenance') as artifacts:
            with self.assertRaises(RevError) as caught:
                loader.load_verified('never-read', 'never-read', 'never-read')
            self.assertEqual(caught.exception.kind, 'hardware'); artifacts.assert_not_called()

    def test_supported_candidate_is_not_inference_claim(self):
        report = dict(os='Linux', machine='x86_64', total_ram_bytes=32*hardware.GIB,
                      available_ram_bytes=20*hardware.GIB, cuda_driver_observed=True,
                      nvidia=[dict(index=0, total_bytes=24*hardware.GIB, free_bytes=20*hardware.GIB)])
        result = hardware.require_hardware(report)
        self.assertEqual(result['device'], 'cuda:0'); self.assertTrue(result['candidate']); self.assertFalse(result['verified_inference'])
        report['available_ram_bytes'] = None
        with self.assertRaises(RevError):
            hardware.require_hardware(report)

    @staticmethod
    def capable_report():
        return dict(os='Windows', machine='AMD64', total_ram_bytes=96*hardware.GIB,
                    available_ram_bytes=80*hardware.GIB, nvidia=[dict(index=0,
                    total_bytes=48*hardware.GIB, free_bytes=40*hardware.GIB)])

    def test_windows_modes_dtype_estimates_and_unknown_resources(self):
        report = self.capable_report()
        for device in ('cpu', 'cuda:0', 0, '0', 'cuda'):
            for dtype in hardware.DTYPES:
                self.assertTrue(hardware.require_hardware(report, device, dtype)['candidate'])
        self.assertGreater(hardware.resource_estimate('cpu', 'fp32')['host_bytes'],
                           hardware.resource_estimate('cpu', 'bf16')['host_bytes'])
        for device, dtype in ((True, 'bf16'), (-1, 'bf16'), ('xpu', 'bf16'), ('cuda:-1', 'fp32'), ('cpu', 'int8')):
            with self.assertRaises(RevError) as caught:
                hardware.normalize_mode(device, dtype)
            self.assertEqual(caught.exception.kind, 'configuration')
        for value, message in ((None, 'unknown'), (2*hardware.GIB, 'insufficient')):
            with patch.object(loader, 'diagnose', return_value=dict(report, available_ram_bytes=value)), patch.object(loader, 'locked_provenance') as artifacts:
                with self.assertRaises(RevError) as caught:
                    loader.load_verified('unused', 'unused', 'unused', 'cpu', 'fp32')
                self.assertIn(message, caught.exception.action); artifacts.assert_not_called()

    def test_actual_torch_capability_and_resource_change_before_load(self):
        torch = MagicMock()
        torch.cuda.is_available.return_value = False
        with self.assertRaises(RevError) as caught:
            hardware.require_runtime(torch, self.capable_report(), 'cuda:0')
        self.assertIn('no requested CUDA', caught.exception.action)
        torch.cuda.is_available.return_value = True
        torch.cuda.device_count.return_value = 1
        torch.cuda.is_bf16_supported.return_value = False
        with self.assertRaises(RevError) as caught:
            hardware.require_runtime(torch, self.capable_report(), 'cuda:0')
        self.assertIn('cannot provide bf16', caught.exception.action)
        torch.cuda.mem_get_info.return_value = (40*hardware.GIB, 48*hardware.GIB)
        hardware.require_runtime(torch, self.capable_report(), 'cuda:0', 'fp16')
        torch.cuda.mem_get_info.return_value = (hardware.GIB, 48*hardware.GIB)
        with self.assertRaises(RevError):
            hardware.require_runtime(torch, self.capable_report(), 'cuda:0', 'fp16')
        torch.ones.side_effect = RuntimeError('kernel unavailable')
        with self.assertRaises(RevError) as caught:
            hardware.require_runtime(torch, self.capable_report(), 'cpu', 'fp16')
        self.assertIn('kernels', caught.exception.action)

    def test_real_windows_cpu_cuda_loader_warm_service_and_readiness_dtype_flow(self):
        # Heavy dependencies/artifacts are fixtures; verified loader, official
        # Scorer constructor/warm, serve and readiness validation actually run.
        class Linear:
            def __init__(self, *args, **kwargs):
                self.weight = MagicMock()
            def load_state_dict(self, value): pass
            def __call__(self, value): return MagicMock()
        for device, dtype in ((device, dtype) for device in ('cpu', 'cuda:0') for dtype in hardware.DTYPES):
            with self.subTest(device=device, dtype=dtype), tempfile.TemporaryDirectory() as directory:
                raw = b'fixture checkpoint, never pickle'
                checkpoint = Path(directory)/'checkpoint.pt'; checkpoint.write_bytes(raw)
                lock, metadata, source = loader.locked_provenance()
                lock = copy.deepcopy(lock)
                lock['adapter']['artifacts']['checkpoint.pt'] = hashlib.sha256(raw).hexdigest()
                torch = MagicMock(); torch.nn.Linear = Linear
                torch.cuda.is_available.return_value = True
                torch.cuda.device_count.return_value = 1
                torch.cuda.mem_get_info.return_value = (40*hardware.GIB, 48*hardware.GIB)
                transformers = MagicMock()
                backbone = transformers.AutoModelForImageTextToText.from_pretrained.return_value.eval.return_value.model.language_model
                backbone.named_modules.return_value = [('q_proj', Linear())]
                backbone.config.hidden_size = 4
                backbone.parameters.return_value = iter([types.SimpleNamespace(device=device)])
                transformers.AutoTokenizer.from_pretrained.return_value.encode.return_value = [1, 2]
                torch.load.return_value = dict(metadata=dict(model=lock['base']['repo'], revision=lock['base']['revision'], temperature=1.96, state_format='raw'),
                    adapters={'q_proj': dict(a=MagicMock(), b=MagicMock())}, headq={}, headk={})
                with patch.object(loader, 'diagnose', return_value=self.capable_report()), patch.object(loader, 'locked_provenance', return_value=(lock, metadata, source)), patch.object(loader, 'verify_environment'), patch.object(loader, 'verify_base', return_value=Path(directory)), patch.object(loader.c, 'verify_artifacts'), patch.dict(sys.modules, torch=torch, transformers=transformers):
                    scorer = loader.load_verified(directory, directory, 'fixture-lock', device, dtype)
                    self.assertTrue(scorer.info['warmed']); self.assertTrue(scorer.info['ready'])
                    kwargs = transformers.AutoModelForImageTextToText.from_pretrained.call_args.kwargs
                    self.assertEqual(kwargs['device_map'], device)
                    self.assertIs(kwargs['dtype'], getattr(torch, hardware.DTYPES[dtype]))
                    self.assertTrue(kwargs['local_files_only']); self.assertFalse(kwargs['trust_remote_code'])
                    if device == 'cpu':
                        torch.cuda.is_available.assert_not_called(); torch.backends.cuda.enable_cudnn_sdp.assert_not_called()
                    else:
                        torch.cuda.is_available.assert_called_once()
                        torch.backends.cuda.enable_cudnn_sdp.assert_called_once_with(False)
                    info = dict(scorer.info, checkpoint_sha256=ready_info()['checkpoint_sha256'])
                    worker = Mock(info=info)
                    server = MagicMock(); server.__enter__.return_value = server; server.stopping = True
                    server.connection_info = service.connection_for('http://127.0.0.1:12345', 'fixture', 'REV_AUTH_TOKEN')
                    with patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(service, 'Worker', return_value=worker) as factory, patch.object(service, 'make_server', return_value=server):
                        service.serve(Path(directory)/'state.json', 'REV_AUTH_TOKEN', 'fixture', directory, directory, 'fixture-lock', device, dtype)
                    self.assertEqual(factory.call_args.args[0]['device'], device)
                    self.assertEqual(factory.call_args.args[0]['dtype'], dtype)
                    worker.close.assert_called_once()

    def test_resource_recheck_precedes_checkpoint_deserialization(self):
        report = self.capable_report()
        lock, metadata, source = loader.locked_provenance()
        torch = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'checkpoint.pt').write_bytes(b'fixture')
            with patch.object(loader, 'diagnose', side_effect=[report, dict(report, available_ram_bytes=hardware.GIB)]), patch.object(loader, 'locked_provenance', return_value=(lock, metadata, source)), patch.object(loader, 'verify_environment'), patch.object(loader, 'verify_base'), patch.object(loader.c, 'verify_artifacts'), patch.dict(sys.modules, torch=torch, transformers=MagicMock()):
                with self.assertRaises(RevError) as caught:
                    loader.load_verified(directory, directory, 'fixture', 'cpu')
                self.assertEqual(caught.exception.kind, 'hardware'); torch.load.assert_not_called()

    def test_missing_environment_model_and_service_remain_distinct_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory)/'missing'
            with patch.object(loader, 'diagnose', return_value=self.capable_report()), patch.object(loader, 'verify_base') as base:
                with self.assertRaises(RevError):
                    loader.load_verified(directory, directory, missing, 'cpu', 'fp32')
                base.assert_not_called()
            lock, metadata, _ = loader.locked_provenance()
            with self.assertRaises(RevError) as caught:
                loader.verify_base(missing, lock, metadata)
            self.assertEqual(caught.exception.kind, 'integrity')
            connection = service.connection_for('http://127.0.0.1:12345', 'fixture', 'REV_AUTH_TOKEN')
            with patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(selector.http.client, 'HTTPConnection') as transport:
                transport.return_value.request.side_effect = ConnectionRefusedError()
                with self.assertRaises(RevError) as caught:
                    selector.Client(connection).ready()
                self.assertEqual(caught.exception.kind, 'service')

    def test_start_cli_and_spawn_preserve_device_dtype_and_cleanup(self):
        argv = ['service.py', 'start', '--state', 'fixture', '--base', 'base', '--adapter', 'adapter', '--environment', 'lock', '--device', 'cpu', '--dtype', 'fp32']
        with patch.object(sys, 'argv', argv), patch.object(service, 'ensure_started', return_value={}) as start, patch('builtins.print'):
            self.assertEqual(service.main(), 0)
            self.assertEqual(start.call_args.args[-1], 'cpu')
            self.assertEqual(start.call_args.kwargs['dtype'], 'fp32')
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(hardware, 'diagnose', return_value=self.capable_report()), patch.object(service, 'venv_interpreter', return_value='fixture-python'), patch.object(service.subprocess, 'Popen') as spawn:
            spawn.return_value.poll.return_value = 1
            with self.assertRaises(RevError) as caught:
                service.ensure_started(Path(directory)/'state.json', 'fixture-python', 'base', 'adapter', 'lock', device='cpu', dtype='fp32')
            self.assertEqual(caught.exception.kind, 'startup')
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index('--device')+1], 'cpu')
            self.assertEqual(command[command.index('--dtype')+1], 'fp32')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_reuse_never_silently_changes_selected_mode(self):
        with ServerFixture() as fixture, tempfile.TemporaryDirectory() as directory:
            state = Path(directory)/'state.json'
            service.write_exclusive(state, dict(connection=fixture.server.connection_info, pid=os.getpid()))
            with patch.object(service.subprocess, 'Popen') as spawn:
                with self.assertRaises(RevError) as caught:
                    service.ensure_started(state, 'unused', 'unused', 'unused', 'unused', device='cpu', dtype='fp32')
                self.assertEqual(caught.exception.kind, 'configuration'); spawn.assert_not_called()

    def test_integrity_errors_before_execution_or_deserialization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'checkpoint.pt'; path.write_bytes(b'fixture, not pickle')
            with self.assertRaises(RevError):
                loader.checked_bytes(path, '0'*64)
            self.assertEqual(loader.checked_bytes(path, hashlib.sha256(path.read_bytes()).hexdigest()), path.read_bytes())
            with self.assertRaises(RevError):
                loader.verify_environment(BUNDLE/'assets/rev/environment.lock.template.json', {})

    def test_unisolated_environment_rejected_before_any_dependency_import(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory)/'environment.json'
            receipt.write_text(json.dumps(dict(schema=1, resolved=True, venv=sys.prefix, distributions={})))
            with patch.object(loader.importlib.metadata, 'distributions') as distributions:
                with self.assertRaises(RevError):
                    loader.verify_environment(receipt, {'dependencies': {}})
                distributions.assert_not_called()

    def test_base_git_blob_identity_and_unlisted_code(self):
        names = ['config.json','tokenizer_config.json','tokenizer.json','vocab.json','merges.txt',
                 'model.safetensors.index.json','weights.safetensors']
        with tempfile.TemporaryDirectory() as directory:
            metadata = {'siblings': []}
            for name in names:
                raw = b'{"weight_map":{"w":"weights.safetensors"}}' if name == 'model.safetensors.index.json' else b'fixture'
                (Path(directory)/name).write_bytes(raw)
                metadata['siblings'].append(dict(rfilename=name, size=len(raw), blobId=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()))
            lock = {'base': {'artifacts': {'weights.safetensors': hashlib.sha256(b'fixture').hexdigest()}}}
            loader.verify_base(directory, lock, metadata)
            (Path(directory)/'evil.py').write_text('raise AssertionError("not executed")')
            with self.assertRaises(RevError):
                loader.verify_base(directory, lock, metadata)
            (Path(directory)/'evil.py').unlink(); (Path(directory)/'config.json').write_bytes(b'changed')
            with self.assertRaises(RevError):
                loader.verify_base(directory, lock, metadata)

    def test_client_timeout_and_transport_error_no_fallback(self):
        connection = service.connection_for('http://127.0.0.1:12345', 'test', 'REV_AUTH_TOKEN')
        for error, kind in ((TimeoutError(), 'timeout'), (OSError(), 'service')):
            with patch.dict(os.environ, REV_AUTH_TOKEN=TOKEN), patch.object(selector.http.client, 'HTTPConnection') as transport:
                transport.return_value.request.side_effect = error
                with self.assertRaises(RevError) as caught:
                    selector.Client(connection).call('/ping')
                self.assertEqual(caught.exception.kind, kind)
                transport.return_value.close.assert_called_once()

    def test_worker_timeout_terminates_owned_process(self):
        worker = service.Worker.__new__(service.Worker)
        worker.pipe = Mock(); worker.pipe.poll.return_value = False
        worker.process = Mock(); worker.process.is_alive.side_effect = [True, False]
        worker.ready = True
        with self.assertRaises(RevError) as caught:
            worker.receive(.001, 'result')
        self.assertEqual(caught.exception.kind, 'timeout')
        worker.process.terminate.assert_called_once(); self.assertFalse(worker.ready)

    def test_worker_exit_invalidates_readiness_before_next_score(self):
        worker = service.Worker.__new__(service.Worker)
        worker.process = Mock(); worker.process.is_alive.return_value = False
        worker.pipe = Mock(); worker.ready = True
        self.assertFalse(worker.is_ready())
        with self.assertRaises(RevError) as caught:
            worker.score(c.score_request(context(), selector.INSTRUCTIONS))
        self.assertEqual(caught.exception.kind, 'readiness')
        worker.pipe.send.assert_not_called()

    def test_venv_identity_with_no_site_legacy_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            binary = root / ('Scripts' if os.name == 'nt' else 'bin') / 'python'
            binary.parent.mkdir(); binary.write_bytes(b'fixture interpreter identity only')
            (root / 'pyvenv.cfg').write_text('include-system-site-packages = false\n')
            self.assertEqual(service.venv_interpreter(binary), binary)
            with patch.object(loader.sys, 'executable', str(binary)), patch.object(loader.sys, 'prefix', str(root/'base')), patch.object(loader.sys, 'base_prefix', str(root/'base')):
                self.assertEqual(loader.isolated_prefix({'venv': str(root)}), root)
                with self.assertRaises(RevError):
                    loader.isolated_prefix({'venv': str(root/'different')})
            (root / 'pyvenv.cfg').unlink()
            with self.assertRaises(RevError):
                service.venv_interpreter(binary)
            with patch.object(loader.sys, 'executable', str(binary)):
                with self.assertRaises(RevError):
                    loader.isolated_prefix({'venv': str(root)})

    def test_ready_metadata_rejects_boolean_numeric_aliases_and_invalid_device(self):
        connection = service.connection_for('http://127.0.0.1:12345', 'fixture_runtime', 'REV_AUTH_TOKEN')
        info = dict(ready_info(), runtime_id='fixture_runtime', lock_sha256=connection['lock_sha256'],
                    runtime_version='0.4.0', pid=os.getpid())
        selector.validate_ready(info, connection)
        for key, value in (('ready', 1), ('warmed', 1), ('max_row_tokens', 16384.0), ('device', 'cuda:unknown')):
            with self.assertRaises(RevError):
                selector.validate_ready(dict(info, **{key: value}), connection)

    def test_duplicate_json_and_nonfinite_are_rejected(self):
        for raw in (b'{"answers":{},"answers":{}}', b'{"value":NaN}'):
            with self.assertRaises(ValueError):
                selector.strict_json(raw)


class MemoryPlanTests(unittest.TestCase):
    def test_bounded_mode_requires_explicit_directory_and_known_probe(self):
        for options in (dict(memory_mode='unrecognized'), dict(memory_mode='bounded-cpu'),
                        dict(memory_mode='bounded-cpu', offload_directory='fixture', device='cuda:0')):
            with patch.object(loader, 'locked_provenance') as artifacts, self.assertRaises(RevError):
                loader.load_verified('unused', 'unused', 'unused', **options)
            artifacts.assert_not_called()
        with patch.object(loader, 'memory_status', return_value=dict(total_ram_bytes=None, available_ram_bytes=None)), patch.object(loader, 'locked_provenance') as artifacts:
            with self.assertRaises(RevError):
                loader.load_verified('unused', 'unused', 'unused', device='cpu', memory_mode='bounded-cpu', offload_directory='fixture')
            artifacts.assert_not_called()

    def test_tensor_derived_modes_unknown_resources_and_long_row(self):
        catalog = {'embed_tokens.weight': dict(shape=[248320, 2560]),
                   **{'layers.%d.weight' % i: dict(shape=[9216, 2560]) for i in range(96)}}
        report = dict(total_ram_bytes=16*hardware.GIB, available_ram_bytes=4*hardware.GIB)
        plan = hardware.execution_plan(report, catalog, row_token_budget=256)
        self.assertEqual(plan['mode'], 'bounded-cpu')
        self.assertEqual(plan['largest_dense_block_bytes'], 9216*2560*2)
        self.assertEqual(plan['largest_materialized_block_bytes'], 9216*2560*2)
        self.assertEqual(plan['largest_source_tensor_bytes'], 248320*2560*2)
        self.assertIsNone(plan['measured_peak_bytes']); self.assertFalse(plan['verified_inference'])
        for options in (dict(mode='full-resident'), dict(row_token_budget=16384),
                        dict(process_budget_bytes=4*hardware.GIB)):
            with self.assertRaises(RevError):
                hardware.execution_plan(report, catalog, **options)
        for key in report:
            with self.assertRaises(RevError):
                hardware.execution_plan(dict(report, **{key: None}), catalog)
        with self.assertRaises(RevError):
            hardware.execution_plan(report, {})

    def test_compact_embedding_plan_528_and_exact_shared_contract(self):
        catalog = {'embed_tokens.weight': dict(shape=[248320, 2560]),
                   'layers.0.weight': dict(shape=[9216, 2560]), 'norm.weight': dict(shape=[2560])}
        report = dict(total_ram_bytes=16847327232, available_ram_bytes=3823661056)
        for dtype, width in (('bf16', 2), ('fp16', 2), ('fp32', 4)):
            plan = hardware.execution_plan(report, catalog, dtype=dtype, row_token_budget=528)
            compact = plan['embedding']
            self.assertEqual(compact, offload.embedding_contract([248320,2560], hardware.DTYPES[dtype], 528))
            self.assertEqual(compact['output_bytes'], 528*2560*width)
            self.assertEqual(compact['indices_bytes'], 528*8)
            self.assertEqual(compact['row_buffer_bytes'], 2560*width)
            self.assertEqual(compact['working_set_bytes'], 529*2560*width+528*8+256*1024)
            self.assertEqual(plan['materialization_reserve_bytes'], 9216*2560*width+256*1024)
            self.assertEqual(plan['estimated_process_bytes'], plan['runtime_reserve_bytes']+
                plan['pointer_head_bytes']+plan['activation_reserve_bytes']+plan['materialization_reserve_bytes'])
            with self.assertRaises(RevError):
                hardware.execution_plan(report, catalog, dtype=dtype, row_token_budget=528,
                                        process_budget_bytes=plan['estimated_process_bytes']-1)
        roomy = dict(total_ram_bytes=32*hardware.GIB, available_ram_bytes=24*hardware.GIB)
        batch = hardware.execution_plan(roomy, catalog, row_token_budget=17, embedding_batch_budget=2)
        self.assertEqual(batch['embedding']['max_row_tokens'], 32)
        self.assertEqual(batch['embedding']['max_ids'], 64)
        embedding_only = hardware.execution_plan(roomy, {'embed_tokens.weight':catalog['embed_tokens.weight'],
                                                         'norm.weight':catalog['norm.weight']}, row_token_budget=528)
        self.assertEqual(embedding_only['materialization_reserve_bytes'], embedding_only['embedding']['working_set_bytes'])
        for options in (dict(embedding_batch_budget=0), dict(embedding_batch_budget=True),
                        dict(embedding_batch_budget=17), dict(embedding_batch_budget=2, row_token_budget=16384),
                        dict(safety_margin_bytes=hardware.GIB-1), dict(process_budget_bytes=report['available_ram_bytes']),
                        dict(process_budget_bytes=100)):
            with self.assertRaises(RevError):
                hardware.execution_plan(report, catalog, **options)
        with self.assertRaises(RevError):
            hardware.execution_plan(dict(report, available_ram_bytes=None), catalog)
        # Fresh RAM can reduce an external ceiling; it cannot authorize overspend.
        with self.assertRaises(RevError):
            hardware.execution_plan(dict(report, available_ram_bytes=hardware.GIB+100), catalog,
                                    process_budget_bytes=2*hardware.GIB, budget_is_ceiling=True)

    def test_smoke_ceiling_covers_observed_startup_without_spending_system_reserves(self):
        smoke = import_module(PACKAGE + '.smoke')
        catalog = {'embed_tokens.weight': dict(shape=[248320, 2560]),
                   'layers.0.weight': dict(shape=[9216, 2560])}
        report = dict(total_ram_bytes=16847327232, available_ram_bytes=4092387328)
        plan = smoke.smoke_plan(report, catalog, 'bf16', 528)
        self.assertEqual(plan['process_budget_bytes'], 2554225664)
        self.assertEqual(plan['observed_startup_job_commit_bytes'], 1986588672)
        self.assertGreater(plan['process_budget_bytes'], plan['required_startup_budget_bytes'])
        self.assertGreater(plan['observed_startup_job_commit_bytes'],
                           plan['estimated_process_bytes']+128*1024**2)
        self.assertEqual(plan['process_budget_bytes']+plan['safety_margin_bytes']+
                         plan['supervisor_reserve_bytes'], report['available_ram_bytes'])
        # The old estimate fits here, but observed startup plus headroom does not.
        tight = dict(report, available_ram_bytes=plan['safety_margin_bytes']+
                     plan['supervisor_reserve_bytes']+plan['required_startup_budget_bytes']-1)
        with self.assertRaises(RevError):
            smoke.smoke_plan(tight, catalog, 'bf16', 528)
        boundary = dict(tight, available_ram_bytes=tight['available_ram_bytes']+1)
        admitted = smoke.smoke_plan(boundary, catalog, 'bf16', 528)
        self.assertEqual(admitted['process_budget_bytes'], admitted['required_startup_budget_bytes'])

    def test_fresh_resource_and_process_guards(self):
        plan = dict(safety_margin_bytes=hardware.GIB, process_budget_bytes=2*hardware.GIB)
        process = dict(rss_bytes=hardware.GIB, private_bytes=hardware.GIB)
        hardware.check_plan(plan, dict(available_ram_bytes=2*hardware.GIB), process)
        for report, counters in ((dict(available_ram_bytes=None), process),
                                 (dict(available_ram_bytes=hardware.GIB-1), process),
                                 (dict(available_ram_bytes=2*hardware.GIB), dict(process, private_bytes=3*hardware.GIB)),
                                 (dict(available_ram_bytes=2*hardware.GIB), dict(process, peak_rss_bytes=3*hardware.GIB)),
                                 (dict(available_ram_bytes=2*hardware.GIB), dict(process, rss_bytes=None))):
            with self.assertRaises(RevError):
                hardware.check_plan(plan, report, counters)

    def test_derived_output_cannot_overlap_originals_or_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for output in (root, root/'base', root/'base/derived'):
                with self.assertRaises(RevError):
                    offload.disjoint_destination(output, [root/'base'])
            offload.disjoint_destination(root/'derived', [root/'base', root/'runtime'])


@unittest.skipUnless('torch' in sys.modules and hasattr(sys.modules['torch'], '__version__'),
                     'Requires explicitly verified isolated Torch environment; offline fixtures do not imply inference')
class ActualMappedTensorTests(unittest.TestCase):
    """Small REAL Qwen3.5 tensor operations, never evidence of full Rev inference."""
    def test_compact_embedding_bitwise_reads_bounds_recovery_and_options(self):
        import torch
        for dtype in (torch.bfloat16, torch.float16, torch.float32):
            with self.subTest(dtype=str(dtype)), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                # Padding is deliberately nonzero; inference must copy stored values.
                reference = ((torch.arange(20000*8).reshape(20000,8) % 103 - 51) / 16).to(dtype)
                bits_dtype = torch.int32 if dtype == torch.float32 else torch.int16
                patterns = ([-2147483648,2139095040,2143289345,1] if dtype == torch.float32 else
                            [-32768,32640,32705,1] if dtype == torch.bfloat16 else [-32768,31744,32257,1])
                reference.view(bits_dtype)[0,:4] = torch.tensor(patterns,dtype=bits_dtype)
                raw = reference.view(torch.uint8).numpy().tobytes()
                filename = hashlib.sha256(b'embed_tokens.weight').hexdigest()+'.bin'
                path = directory/filename
                path.write_bytes(raw)
                item = dict(file=filename, sha256=hashlib.sha256(raw).hexdigest(),
                            shape=[20000,8], dtype=str(dtype).split('.')[-1], bytes=len(raw))
                model = torch.nn.Module()
                model.embed_tokens = torch.nn.Embedding(20000,8,padding_idx=0,device='meta',dtype=dtype)
                model.layers = torch.nn.ModuleList()
                model.norm = torch.nn.Identity()
                model.eval()
                original = model.embed_tokens.weight
                contract = offload.embedding_contract([20000,8], item['dtype'], 16, 2)
                manifest = dict(tensors={'embed_tokens.weight':item})
                handles = offload.attach_mapped_blocks(model, directory, manifest, embedding_plan=contract)
                ids = torch.tensor([[0,19999,1,19999], [5,0,5,1]], dtype=torch.int64)
                events = []
                real_open = Path.open
                fault = [False]
                class ObservedFile:
                    def __init__(self, stream): self.stream = stream
                    def __enter__(self): return self
                    def __exit__(self, *args): self.stream.close()
                    def __getattr__(self, name): return getattr(self.stream, name)
                    def seek(self, offset):
                        events.append(('seek', offset))
                        return self.stream.seek(offset)
                    def readinto(self, buffer):
                        events.append(('readinto', len(buffer)))
                        if fault[0] and len(buffer) == contract['row_buffer_bytes']:
                            fault[0] = False
                            raise OSError('isolated row read failure')
                        return self.stream.readinto(buffer)
                def observed_open(target, *args, **kwargs):
                    self.assertEqual(target, path)
                    self.assertEqual(kwargs.get('buffering'), 0)
                    return ObservedFile(real_open(target, *args, **kwargs))
                allocations = []
                real_empty = torch.empty
                def observed_empty(shape, **kwargs):
                    allocations.append(tuple(shape))
                    self.assertLessEqual(__import__('math').prod(shape)*reference.element_size(), contract['output_bytes'])
                    return real_empty(shape, **kwargs)
                with torch.inference_mode(), patch.object(Path, 'open', observed_open), \
                     patch.object(torch, 'from_file', side_effect=AssertionError('full embedding mapping forbidden')), \
                     patch.object(torch, 'empty', observed_empty):
                    for index_type in (torch.int64, torch.int32):
                        events.clear()
                        actual = model.embed_tokens(input=ids.to(index_type))
                        expected = torch.nn.functional.embedding(ids, reference, padding_idx=0)
                        self.assertEqual(actual.dtype, dtype)
                        self.assertEqual(tuple(actual.shape), (2,4,8))
                        self.assertTrue(torch.equal(actual.view(torch.uint8), expected.view(torch.uint8)))
                        self.assertEqual([n for event,n in events if event == 'seek'],
                                         [index*contract['row_buffer_bytes'] for index in ids.reshape(-1).tolist()])
                        self.assertEqual(sum(event == 'readinto' and n == contract['row_buffer_bytes']
                                             for event,n in events), ids.numel())
                        self.assertTrue(all(n in (contract['row_buffer_bytes'], offload.INTEGRITY_BUFFER_BYTES)
                                            for event,n in events if event == 'readinto'))
                    limit_ids = torch.tensor([[0,19999]*8, [1,5]*8])
                    events.clear()
                    limit_output = model.embed_tokens(limit_ids)
                    self.assertEqual(limit_output.numel()*limit_output.element_size(), contract['output_bytes'])
                    self.assertEqual(sum(event == 'seek' for event,n in events), contract['max_ids'])
                    self.assertTrue(torch.equal(limit_output.view(torch.uint8), reference[limit_ids].view(torch.uint8)))
                    fault[0] = True
                    with self.assertRaises(OSError): model.embed_tokens(ids)
                    self.assertIs(model.embed_tokens.weight, original)
                    self.assertTrue(torch.equal(model.embed_tokens(ids).view(torch.uint8), expected.view(torch.uint8)))
                self.assertEqual(set(allocations), {(2,4,8), (2,16,8)})
                strided_ids = ids[:,::2]
                self.assertFalse(strided_ids.is_contiguous())
                self.assertTrue(torch.equal(model.embed_tokens(strided_ids).view(torch.uint8), reference[strided_ids].view(torch.uint8)))
                bad = [ids.float(), ids.short(), ids.bool(), ids.to('meta'), ids[0], ids[0,0],
                       ids.unsqueeze(0), torch.empty((0,4),dtype=torch.long),
                       torch.zeros((3,4),dtype=torch.long), torch.zeros((1,17),dtype=torch.long),
                       torch.tensor([[20000]]), torch.tensor([[-1]]), torch.zeros(10000,dtype=torch.long)[:4].view(1,4)]
                with patch.object(Path, 'open', side_effect=AssertionError('invalid IDs must fail before reads')):
                    for input in bad:
                        with self.subTest(shape=list(input.shape), input_dtype=str(input.dtype)), self.assertRaises(RevError):
                            model.embed_tokens(input)
                    for option,value in [('max_norm',1.0), ('norm_type',1.0), ('scale_grad_by_freq',True), ('sparse',True), ('training',True)]:
                        with patch.object(model.embed_tokens, option, value), self.assertRaises(RevError):
                            model.embed_tokens(ids)
                # Authenticating every call catches changed bytes before output allocation.
                path.write_bytes(bytes([raw[0]^1])+raw[1:])
                with patch.object(torch,'empty',side_effect=AssertionError('tamper must precede output')), self.assertRaises(RevError):
                    model.embed_tokens(ids)
                path.write_bytes(raw[:-1])
                with self.assertRaises(RevError): model.embed_tokens(ids)
                path.write_bytes(raw)
                for handle in handles: handle.remove()
                self.assertIs(model.embed_tokens.weight, original)
                self.assertNotIn('forward', model.embed_tokens.__dict__)
                # Even identical values cannot make a tied embedding alias bounded.
                model.norm = torch.nn.Module()
                model.norm.register_parameter('weight', original)
                aliased = dict(tensors={**manifest['tensors'], 'norm.weight':dict(item)})
                with self.assertRaises(RevError):
                    offload.attach_mapped_blocks(model, directory, aliased, embedding_plan=contract)
                self.assertNotIn('forward', model.embed_tokens.__dict__)
                self.assertFalse(model.norm._forward_hooks)
                model.norm = torch.nn.Identity()
                model.extra_embedding_alias = model.embed_tokens
                with self.assertRaises(RevError):
                    offload.attach_mapped_blocks(model, directory, manifest, embedding_plan=contract)
                del model.extra_embedding_alias
                for option,value in [('max_norm',1.0), ('norm_type',1.0), ('scale_grad_by_freq',True), ('sparse',True)]:
                    with patch.object(model.embed_tokens, option, value), self.assertRaises(RevError):
                        offload.attach_mapped_blocks(model, directory, manifest, embedding_plan=contract)
                    self.assertNotIn('forward', model.embed_tokens.__dict__)

    def test_qwen_stream_merge_repeated_forward_and_tamper(self):
        import torch
        from accelerate import init_empty_weights
        from safetensors.torch import save_file
        from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5TextConfig
        from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5TextModel
        torch.set_num_threads(1)
        for dtype in (torch.float32, torch.bfloat16, torch.float16):
            with self.subTest(dtype=str(dtype)), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                config = Qwen3_5TextConfig(vocab_size=64, hidden_size=32, intermediate_size=64,
                    num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=1, head_dim=16,
                    linear_num_key_heads=2, linear_num_value_heads=4, linear_key_head_dim=8,
                    linear_value_head_dim=8, layer_types=['linear_attention', 'full_attention'],
                    rope_parameters=dict(rope_type='default', rope_theta=10000., partial_rotary_factor=1.,
                                         mrope_section=[2, 3, 3]))
                torch.manual_seed(814)
                eager = Qwen3_5TextModel._from_config(config, dtype=dtype, attn_implementation='sdpa').eval()
                # Clone is deliberately confined to this tiny fixture, not production derivation.
                state = {offload.PREFIX + name: value.detach().clone().to(torch.bfloat16)
                         for name, value in eager.state_dict().items()}
                save_file(state, str(directory/'fixture.safetensors'))
                (directory/'model.safetensors.index.json').write_text(json.dumps(
                    dict(weight_map={name: 'fixture.safetensors' for name in state})))
                eager.load_state_dict({name[len(offload.PREFIX):]: value.to(dtype) for name, value in state.items()})
                target = 'layers.0.mlp.up_proj'
                # Binary fractions give exactly representable reference dot products.
                a = (torch.arange(96, dtype=torch.float32).reshape(3, 32) % 13 - 6) / 32
                b = (torch.arange(192, dtype=torch.float32).reshape(64, 3) % 11 - 5) / 32
                pair = {target: dict(a=a, b=b)}
                with torch.no_grad():
                    eager.get_submodule(target).weight.add_((2*(b.float()@a.float())).to(dtype))
                catalog = offload.text_catalog(offload.tensor_catalog(directory))
                identity = dict(source='fixture-source', base='fixture-base', adapter='fixture-adapter',
                                environment='actual-verified-torch', dtype=str(dtype))
                derived = directory/'derived'
                # Force multiple row chunks even for the small fixture.
                with patch.object(offload, 'CHUNK_BYTES', 512):
                    digest = offload.derive(directory, derived, catalog, pair, identity, str(dtype).split('.')[-1])
                    self.assertEqual(digest, offload.derive(directory, derived, catalog, pair, identity, str(dtype).split('.')[-1]))
                manifest = offload.verify_derived(derived, identity, digest)
                merged_item = manifest['tensors'][target+'.weight']
                merged = torch.from_file(str(derived/merged_item['file']), size=64*32, dtype=dtype).reshape(64,32)
                self.assertTrue(torch.equal(merged, eager.get_submodule(target).weight))
                del merged
                with init_empty_weights(include_buffers=False):
                    mapped = Qwen3_5TextModel._from_config(config, dtype=dtype, attn_implementation='sdpa').eval()
                guards = []
                embedding_plan = offload.embedding_contract([64,32], str(dtype).split('.')[-1], 16)
                handles = offload.attach_mapped_blocks(mapped, derived, manifest, lambda: guards.append(1),
                                                       embedding_plan=embedding_plan)
                ids = torch.tensor([[1, 4, 6, 2, 7, 9, 5, 12]])
                with torch.inference_mode():
                    reference = eager(input_ids=ids, use_cache=False).last_hidden_state
                    first = mapped(input_ids=ids, use_cache=False).last_hidden_state
                    second = mapped(input_ids=ids, use_cache=False).last_hidden_state
                torch.testing.assert_close(first, reference, rtol=0.02 if dtype != torch.float32 else 1e-5,
                                           atol=0.02 if dtype != torch.float32 else 1e-5)
                self.assertTrue(torch.equal(first, second))
                self.assertTrue(all(p.device.type == 'meta' for p in mapped.parameters()))
                with self.assertRaises(RevError):
                    offload.derive(directory, derived, catalog, pair, dict(identity, algorithm_sha256='changed'),
                                   str(dtype).split('.')[-1])
                self.assertTrue(guards)
                # A stale/conflicting tied alias must fail rather than silently
                # assigning different weights to the same logical parameter.
                with init_empty_weights(include_buffers=False):
                    tied = Qwen3_5TextModel._from_config(config, dtype=dtype, attn_implementation='sdpa').eval()
                tied.layers[0].mlp.gate_proj.weight = tied.layers[0].mlp.up_proj.weight
                with self.assertRaises(RevError):
                    offload.attach_mapped_blocks(tied, derived, manifest, embedding_plan=embedding_plan)
                # Direct convolution weights were actually executed by the hybrid layer above.
                with patch.object(mapped.layers[0], 'forward', side_effect=RuntimeError('fixture failure')):
                    with torch.inference_mode(), self.assertRaises(RuntimeError):
                        mapped(input_ids=ids, use_cache=False)
                self.assertTrue(all(p.device.type == 'meta' for p in mapped.parameters()))
                with torch.inference_mode():
                    recovered = mapped(input_ids=ids, use_cache=False).last_hidden_state
                self.assertTrue(torch.equal(recovered, first))
                for handle in handles:
                    handle.remove()
                self.assertNotIn('forward', mapped.embed_tokens.__dict__)
                self.assertFalse(any(block._forward_pre_hooks or block._forward_hooks
                                     for block in [*mapped.layers, mapped.norm]))
                with self.assertRaises(RevError):
                    offload.verify_derived(derived, dict(identity, base='wrong'), digest)
                item = next(iter(manifest['tensors'].values()))
                path = derived/item['file']
                raw = path.read_bytes(); path.write_bytes(bytes([raw[0] ^ 1])+raw[1:])
                with self.assertRaises(RevError):
                    offload.verify_derived(derived, identity, digest)
                # Updating the mutable manifest cannot forge the independent expected digest.
                manifest['tensors'][next(iter(manifest['tensors']))]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                (derived/'manifest.json').write_bytes(offload.canonical(manifest))
                with self.assertRaises(RevError):
                    offload.verify_derived(derived, identity, digest)


class CpuAllocationTests(unittest.TestCase):
    def test_options_are_bounded_and_high_realtime_rejected(self):
        for threads in (0, -1, 65, True, 1.5):
            with self.assertRaises(RevError):
                hardware.cpu_options(threads)
        for priority in ('high', 'realtime', 'AboveNormal', None):
            with self.assertRaises(RevError):
                hardware.cpu_options(4, priority)
        self.assertEqual(hardware.cpu_environment(), {})
        self.assertEqual(hardware.cpu_environment(4, 'above-normal'),
                         dict(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4'))

    def test_unowned_priority_cannot_load_or_start(self):
        with patch.object(service, 'Worker') as worker:
            with self.assertRaises(RevError):
                service.serve('unused', 'unused', 'unused', 'b', 'a', 'e', cpu_priority='above-normal')
            worker.assert_not_called()
        with self.assertRaises(RevError):
            hardware.configure_worker_cpu(4, 'above-normal', False)
        with self.assertRaises(RevError):
            service.ensure_started('unused', 'unused', 'b', 'a', 'e', cpu_priority='above-normal')

    def test_worker_cpu_configuration_precedes_loader_and_is_not_loader_identity(self):
        pipe = Mock(); pipe.recv.return_value = ('stop', None)
        scorer = Mock(info={})
        def load(**arguments):
            self.assertEqual(arguments, dict(base_directory='base'))
            configure.assert_called_once_with(2, 'above-normal', True)
            torch.set_num_threads.assert_not_called()
            return scorer
        torch = Mock(); torch.get_num_threads.side_effect = [2, 4]
        allocation = dict(requested_threads=4, worker_pid=123, worker_priority_class=0x8000)
        with patch.object(service.threading, 'Thread'), patch.object(service, 'configure_worker_cpu', return_value=allocation) as configure, patch.object(service, 'load_verified', side_effect=load), patch.dict(sys.modules, torch=torch):
            service._model_worker(pipe, dict(base_directory='base', cpu_threads=4,
                                           cpu_priority='above-normal', cpu_owned_job=True))
        self.assertEqual(pipe.send.call_args_list[0].args[0][0], 'ready')
        self.assertEqual(scorer.info['cpu_allocation']['torch_num_threads'], 4)
        self.assertEqual(scorer.info['cpu_allocation']['preparation_torch_num_threads'], 2)
        self.assertEqual([v.args for v in torch.set_num_threads.call_args_list], [(4,), (2,)])
        pipe.close.assert_called_once()

    def test_priority_failure_closes_pipe_without_loading(self):
        pipe = Mock()
        with patch.object(service.threading, 'Thread'), patch.object(service, 'configure_worker_cpu', side_effect=RevError('resource', 'CPU allocation failed')), patch.object(service, 'load_verified') as load:
            service._model_worker(pipe, dict(cpu_threads=4, cpu_priority='above-normal'))
        load.assert_not_called(); pipe.close.assert_called_once()
        self.assertEqual(pipe.send.call_args.args[0][0], 'error')

    def test_worker_spawn_inherits_thread_environment_and_failure_cleans_up(self):
        context = Mock(); context.Pipe.return_value = (Mock(), Mock())
        with patch.dict(os.environ), patch.object(service.mp, 'get_context', return_value=context), patch.object(service.Worker, 'receive', side_effect=RevError('resource', 'fixture')), patch.object(service.Worker, 'close') as close:
            before = dict(os.environ)
            context.Process.return_value.start.side_effect = lambda: self.assertEqual(os.environ['OMP_NUM_THREADS'], '2')
            with self.assertRaises(RevError):
                service.Worker(dict(cpu_threads=4, cpu_priority='normal'))
            self.assertEqual(dict(os.environ), before)
            context.Process.return_value.start.assert_called_once(); close.assert_called_once()



    def test_preparation_failure_never_touches_torch(self):
        pipe = Mock(); torch = Mock()
        with patch.object(service.threading, 'Thread'), patch.dict(sys.modules, torch=torch), patch.object(service, 'configure_worker_cpu', return_value={}), patch.object(service, 'load_verified', side_effect=RevError('identity', 'strict mismatch')):
            service._model_worker(pipe, dict(cpu_threads=4))
        torch.get_num_threads.assert_not_called(); torch.set_num_threads.assert_not_called()
        self.assertEqual(pipe.send.call_args.args[0], ('error', dict(kind='identity', action='strict mismatch')))
        pipe.close.assert_called_once()

    def test_default_two_normal_and_unspecified_policy(self):
        self.assertIsNone(hardware.preparation_threads())
        self.assertEqual(hardware.preparation_threads(2), 2)
        for threads in (None, 2):
            pipe = Mock(); pipe.recv.return_value = ('stop', None)
            scorer = Mock(info={}); torch = Mock(); torch.get_num_threads.return_value = 2
            with patch.object(service.threading, 'Thread'), patch.dict(sys.modules, torch=torch), patch.object(service, 'configure_worker_cpu', return_value=dict(requested_threads=threads)) as configure, patch.object(service, 'load_verified', return_value=scorer):
                service._model_worker(pipe, dict(cpu_threads=threads))
            configure.assert_called_once_with(hardware.preparation_threads(threads), 'normal', False)
            self.assertEqual(scorer.info['cpu_allocation']['torch_num_threads'], 2)

    def test_inference_switch_mismatch_restores_and_closes(self):
        pipe = Mock(); torch = Mock(); torch.get_num_threads.side_effect = [2, 3]
        with patch.object(service.threading, 'Thread'), patch.dict(sys.modules, torch=torch), patch.object(service, 'configure_worker_cpu', return_value=dict(requested_threads=4)), patch.object(service, 'load_verified', return_value=Mock(info={})):
            service._model_worker(pipe, dict(cpu_threads=4))
        self.assertEqual(pipe.send.call_args.args[0][0], 'error')
        self.assertEqual([v.args for v in torch.set_num_threads.call_args_list], [(4,), (2,)])
        pipe.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
