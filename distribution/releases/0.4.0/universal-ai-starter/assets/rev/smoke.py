"""Explicit actual HTTP smoke in a fresh owned Windows process tree; no activation."""
if not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = 'rev'

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from . import contracts as c, offload
from .errors import RevError, fail
from .hardware import execution_plan, memory_status, cpu_options, cpu_environment, preparation_threads
from .loader import BUNDLE, locked_provenance
from .selector import Client, INSTRUCTIONS, selection_policy
from .service import read_state, safe_destination, venv_interpreter
from .watchdog import OwnedJob, check_sample


# Observed owned-job startup commit, not a model/score minimum or RSS estimate.
OBSERVED_STARTUP_COMMIT_BYTES = 1986588672
SUPERVISOR_RESERVE_BYTES = 128*1024**2


def smoke_plan(resources, catalog, dtype, row_token_budget):
    margin = max(1024**3, resources['total_ram_bytes']//12)
    ceiling = resources['available_ram_bytes']-margin-SUPERVISOR_RESERVE_BYTES
    plan = execution_plan(resources, catalog, dtype, row_token_budget=row_token_budget,
                          process_budget_bytes=ceiling)
    required = max(plan['estimated_process_bytes'], OBSERVED_STARTUP_COMMIT_BYTES)+SUPERVISOR_RESERVE_BYTES
    plan.update(observed_startup_job_commit_bytes=OBSERVED_STARTUP_COMMIT_BYTES,
                startup_headroom_bytes=SUPERVISOR_RESERVE_BYTES,
                required_startup_budget_bytes=required, safe_ceiling_bytes=ceiling,
                supervisor_reserve_bytes=SUPERVISOR_RESERVE_BYTES,
                budget_basis='fresh-available-minus-system-margin-and-supervisor-reserve')
    if required > ceiling:
        fail('hardware', 'Estimate/observed startup commit plus 128MiB headroom exceeds safe ceiling; no ML launch')
    return plan


def actual_evidence(ping, response, request):
    # This validates the real worker metadata; fixtures still aren't real evidence.
    c.validate_response(request, response)
    measurement = ping.get('last_score', {})
    if (ping.get('inference_evidence') != 'official-warmup-completed; authenticated-score-evidence-required'
            or measurement.get('evidence') != 'actual-pinned-worker'
            or not ping.get('derived_manifest_sha256') or not measurement.get('encoded_tokens')
            or measurement.get('request_bytes') != len(c.json_bytes(request))
            or measurement.get('encoded_tokens') != ping.get('preflight_encoded_tokens')
            or type(measurement.get('score_seconds')) not in (int, float)
            or not 0 <= measurement['score_seconds'] < float('inf')):
        fail('evidence', 'Missing pinned-worker warmup/score metadata; mock response is not inference')
    return dict(actual_inference=True, response=response, encoded_tokens=measurement['encoded_tokens'],
                request_bytes=measurement['request_bytes'], score_seconds=measurement['score_seconds'])


def owned_gateway(value, runtime_id, membership):
    # Windows venv python.exe may be a redirector, with a different real gateway
    # PID. Only the newly assigned Job's membership, never saved-state ancestry,
    # authorizes this descendant. Authenticated ping must then match this PID.
    if (value['connection']['runtime_id'] != runtime_id
            or value['pid'] not in {row['pid'] for row in membership['processes']}):
        fail('identity', 'State is not in freshly owned job/runtime; no state-PID termination')
    return value['pid']


def run(args):
    output = safe_destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    state = output/'service-state.json'
    evidence = dict(schema=1, kind='actual-local-functional-smoke', status='failed', cleanup='not-started',
        actual_inference=False, authenticated_ping=False, response=None, encoded_tokens=None,
        project_connection_changed=False, started_at=time.time(), device='cpu', dtype=args.dtype,
        memory_mode='bounded-cpu', sample_interval_seconds=.2,
        cpu_options=dict(threads=args.cpu_threads, priority=args.cpu_priority),
        limitations=['Polling may miss RSS spikes; OS job peak commit is also checked.',
                     'Short smoke does not establish 16384-token safety, routing quality or savings.',
                     'OS peak commit differs from RSS/private working set.'])
    process = job = thread = sample_file = None
    stop_event = threading.Event(); monitor_errors = []; samples = []
    deadline = time.monotonic()+args.total_timeout
    token_env = 'REV_SMOKE_'+secrets.token_hex(12).upper()
    try:
        cpu_options(args.cpu_threads, args.cpu_priority)
        if not (0 < args.load_timeout <= 1800 and 0 < args.score_timeout <= 900
                and args.load_timeout+args.score_timeout+30 <= args.total_timeout <= 3300):
            fail('configuration', 'Require load<=1800/score<=900/total<=3300 seconds with 30s reserve')
        resources = memory_status(); evidence['resources_before'] = resources
        if any(type(value) is not int or value <= 0 for value in resources.values()):
            fail('hardware', 'Fresh total/available RAM unavailable; no model launch')
        lock, _, _ = locked_provenance()
        evidence['pins'] = dict(source=lock['source']['revision'], base=lock['base']['revision'],
            adapter=lock['adapter']['revision'], checkpoint=lock['adapter']['artifacts']['checkpoint.pt'])
        with open(args.environment, 'rb') as stream:
            evidence['environment_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        evidence['runtime_source_sha256'] = {}
        for name in ('loader.py', 'offload.py', 'hardware.py', 'service.py', 'smoke.py', 'watchdog.py', 'selector.py'):
            with open(BUNDLE/'assets/rev'/name, 'rb') as stream:
                evidence['runtime_source_sha256'][name] = hashlib.file_digest(stream, 'sha256').hexdigest()
        catalog = offload.text_catalog(offload.tensor_catalog(Path(args.base)))
        if getattr(args, 'skip_full_resident_preflight', False):
            evidence['full_resident_admission'] = dict(actual_load=False, evaluated=False,
                reason='Explicitly skipped unchanged full-resident planning; previous rejection retained in attempt-01 evidence; bounded admission still required')
        else:
            try:
                resident = execution_plan(resources, catalog, args.dtype, mode='full-resident',
                                          row_token_budget=args.row_token_budget)
                evidence['full_resident_admission'] = dict(admitted=True, plan=resident, actual_load=False)
            except RevError as error:
                width = 4 if args.dtype == 'fp32' else 2
                weights = sum(__import__('math').prod(item['shape'])*width for item in catalog.values())
                evidence['full_resident_admission'] = dict(admitted=False, actual_load=False,
                    weights_bytes=weights, resources=resources, reason=error.action,
                    estimate_is_measured_minimum=False)
        margin = max(1024**3, resources['total_ram_bytes']//12)
        evidence['attempted_plan'] = dict(mode='bounded-cpu', dtype=args.dtype,
            row_token_budget=args.row_token_budget, safety_margin_bytes=margin,
            gateway_reserve_bytes=128*1024**2,
            process_budget_bytes=resources['available_ram_bytes']-margin-128*1024**2)
        plan = smoke_plan(resources, catalog, args.dtype, args.row_token_budget)
        evidence['selected_plan'] = plan
        body = c.score_request(dict(task='수정 함수에 빈 입력 검사를 추가하고 관련 테스트를 실행한다.',
            goal='기존 동작과 프로젝트 사실을 보존한다.', facts=['Windows 로컬 Python 프로젝트'],
            constraints=['파일 삭제와 외부 전송 금지', '결제와 전역 설정 변경 금지'],
            risks=['빈 입력 처리로 기존 반환값이 달라질 수 있음'], uncertainty=[], dependencies=[]), INSTRUCTIONS)
        evidence.update(request=body, request_bytes=len(c.json_bytes(body)))
        with open(output/'request.json', 'xb') as stream:
            stream.write(c.json_bytes(body))
        environment = dict(os.environ)
        for key in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
            environment.pop(key, None)
        os.environ[token_env] = secrets.token_urlsafe(48)
        environment[token_env] = os.environ[token_env]
        environment.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
            HF_HOME=str(output/'cache'), TORCH_HOME=str(output/'torch-cache'), TOKENIZERS_PARALLELISM='false')
        environment.update(cpu_environment(preparation_threads(args.cpu_threads), args.cpu_priority))
        runtime_id = secrets.token_hex(24)
        command = [str(venv_interpreter(args.python)), '-I', '-S', '-B', str(BUNDLE/'assets/rev/service.py'),
            'serve', '--owned-launch-gate', '--state', str(state), '--base', str(args.base),
            '--adapter', str(args.adapter), '--environment', str(args.environment), '--device', 'cpu',
            '--dtype', args.dtype, '--token-env', token_env, '--runtime-id', runtime_id,
            '--memory-mode', 'bounded-cpu', '--offload-directory', str(args.offload_directory),
            '--row-token-budget', str(args.row_token_budget), '--load-timeout', str(args.load_timeout),
            '--score-timeout', str(args.score_timeout), '--process-budget-bytes', str(plan['process_budget_bytes']),
            '--safety-margin-bytes', str(plan['safety_margin_bytes']), '--preflight-request', str(output/'request.json')]
        command += ['--cpu-threads', str(args.cpu_threads), '--cpu-priority', args.cpu_priority]
        fresh = memory_status(); evidence['resources_at_launch'] = fresh
        if type(fresh['available_ram_bytes']) is not int:
            fail('resource', 'RAM decreased since planning; abort before ML launch; no idle RAM wait')
        launch_ceiling = min(plan['process_budget_bytes'],
            fresh['available_ram_bytes']-plan['safety_margin_bytes']-SUPERVISOR_RESERVE_BYTES)
        if launch_ceiling < plan['required_startup_budget_bytes']:
            fail('resource', 'Fresh safe ceiling cannot cover startup headroom; no ML launch or idle RAM wait')
        plan['process_budget_bytes'] = launch_ceiling
        plan['launch_safe_ceiling_bytes'] = launch_ceiling
        command[command.index('--process-budget-bytes')+1] = str(launch_ceiling)
        job = OwnedJob(launch_ceiling)
        with open(output/'service.log', 'xb') as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log, env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW)
        evidence.update(launcher_pid=process.pid, cleanup='pending', launch_at=time.time())
        job.assign(process)
        sample_file = open(output/'samples.jsonl', 'x', encoding='utf-8')
        def monitor():
            try:
                while not stop_event.is_set():
                    sample = job.sample(); samples.append(sample)
                    sample_file.write(json.dumps(sample)+'\n'); sample_file.flush()
                    check_sample(sample, plan['process_budget_bytes'], plan['safety_margin_bytes'], deadline)
                    stop_event.wait(.2)
            except BaseException as error:
                monitor_errors.append(dict(kind=getattr(error, 'kind', 'monitor'),
                    action=error.action if isinstance(error, RevError) else 'Memory monitor failed; owned job stopped'))
                job.terminate()
        check_sample(job.sample(), plan['process_budget_bytes'], plan['safety_margin_bytes'], deadline)
        thread = threading.Thread(target=monitor, daemon=True); thread.start()
        process.stdin.write(b'1'); process.stdin.close()
        startup_deadline = min(deadline, time.monotonic()+args.load_timeout+15)
        while not state.exists():
            if monitor_errors:
                fail(monitor_errors[0]['kind'], monitor_errors[0]['action'])
            if process.poll() is not None:
                fail('startup', 'Owned gateway failed before readiness; inspect sanitized service.log and samples.jsonl')
            if time.monotonic() >= startup_deadline:
                fail('timeout', 'Startup/load deadline expired; stop owned job')
            time.sleep(.1)
        value = read_state(state)
        gateway_pid = owned_gateway(value, runtime_id, job.sample())
        evidence['gateway_pid'] = gateway_pid
        client = Client(value['connection'], timeout=args.score_timeout+15)
        ping = client.ready()
        if ping['pid'] != gateway_pid:
            fail('identity', 'Authenticated gateway PID mismatch')
        evidence.update(authenticated_ping=True, initial_ping=ping, ready_at=time.time(),
            official_warmup_completed=True, encoded_tokens=ping.get('preflight_encoded_tokens'),
            cold_load_seconds=time.time()-evidence['launch_at'])
        allocation = ping.get('cpu_allocation', {})
        sample = job.sample()
        worker_row = next((row for row in sample['processes'] if row['pid'] == allocation.get('worker_pid')), {})
        evidence['cpu_verification_sample'] = sample
        if (allocation.get('worker_pid') not in {row['pid'] for row in sample['processes']}
                or allocation.get('worker_pid') == gateway_pid
                or allocation.get('torch_num_threads') != args.cpu_threads
                or allocation.get('preparation_threads') != 2
                or allocation.get('preparation_torch_num_threads') != 2
                or allocation.get('worker_priority_class') != (0x8000 if args.cpu_priority == 'above-normal' else 0x20)
                or worker_row.get('priority_class') != allocation.get('worker_priority_class')):
            fail('evidence', 'Actual owned ML worker CPU settings were not confirmed; no score')
        evidence['observed_cpu_allocation'] = allocation
        begin = time.monotonic(); response = client.call('/score', body)
        evidence['http_score_seconds'] = time.monotonic()-begin
        ping = client.ready()
        evidence.update(actual_evidence(ping, response, body), final_ping=ping)
        try:
            evidence['selection'] = selection_policy(response)
        except RevError as error:
            evidence['selection'] = dict(status=error.kind)
        if monitor_errors:
            fail(monitor_errors[0]['kind'], monitor_errors[0]['action'])
        check_sample(job.sample(), plan['process_budget_bytes'], plan['safety_margin_bytes'], deadline)
        evidence['status'] = 'verified'
    except (RevError, OSError, ValueError, c.ContractError) as error:
        evidence['error'] = dict(kind=getattr(error, 'kind', 'environment'),
            action=error.action if isinstance(error, RevError) else 'Inspect isolated paths and service log; no fallback')
    finally:
        # Monitoring remains active through cleanup; exit-race failures are retained.
        if job:
            try:
                job.terminate()
                if process:
                    process.wait(timeout=10)
                stop_event.set()
                if thread:
                    thread.join(timeout=5)
                final = job.sample()
                cleanup_deadline = time.monotonic()+5
                while final['processes'] and time.monotonic() < cleanup_deadline:
                    time.sleep(.05)
                    final = job.sample()
                evidence['cleanup_sample'] = final
                evidence['remaining_owned_pids'] = [row['pid'] for row in final['processes']]
                evidence['cleanup'] = 'stopped' if not final['processes'] else 'failed'
            except BaseException:
                evidence['cleanup'] = 'failed'
            finally:
                stop_event.set()
                if thread:
                    thread.join(timeout=5)
                job.close()
        # Assignment failure leaves only our unreleased gated child, owned by Popen.
        if process and process.poll() is None:
            process.kill(); process.wait(timeout=10)
        if sample_file:
            sample_file.close()
        os.environ.pop(token_env, None)
        evidence['monitor_errors'] = monitor_errors
        if samples:
            evidence['memory'] = dict(sample_count=len(samples),
                peak_tree_rss_bytes=max(row['rss_bytes'] for row in samples),
                peak_tree_private_bytes=max(row['private_bytes'] for row in samples),
                os_peak_job_commit_bytes=max(row['peak_job_commit_bytes'] for row in samples),
                system_available_low_water_bytes=(min(row['available_ram_bytes'] for row in samples)
                    if all(type(row['available_ram_bytes']) is int for row in samples) else None))
        evidence['finished_at'] = time.time()
        evidence['elapsed_seconds'] = evidence['finished_at']-evidence['started_at']
        if evidence['cleanup'] == 'failed' or monitor_errors:
            evidence['status'] = 'failed'
        with open(output/'evidence.json', 'x', encoding='utf-8') as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2)
    return evidence


def main():
    parser = argparse.ArgumentParser(description='Windows 소유 프로세스 watchdog과 인증된 실제 Rev smoke')
    for key in ('base', 'adapter', 'environment', 'python', 'output', 'offload-directory'):
        parser.add_argument('--'+key, required=True)
    parser.add_argument('--dtype', choices=['bf16', 'fp16', 'fp32'], default='bf16')
    parser.add_argument('--cpu-threads', type=int, default=2)
    parser.add_argument('--cpu-priority', choices=['normal', 'above-normal'], default='normal')
    parser.add_argument('--row-token-budget', type=int, default=528)
    parser.add_argument('--load-timeout', type=float, default=1500)
    parser.add_argument('--score-timeout', type=float, default=600)
    parser.add_argument('--total-timeout', type=float, default=2400)
    parser.add_argument('--skip-full-resident-preflight', action='store_true', help='이미 거부된 resident 계획을 반복하지 않는다. bounded 안전 검사는 유지한다')
    parser.add_argument('--allow-local-model-load', required=True, action='store_true')
    result = run(parser.parse_args())
    print(json.dumps({key: result.get(key) for key in ('status', 'actual_inference', 'authenticated_ping', 'cleanup', 'error', 'memory')}, ensure_ascii=False))
    return 0 if result['status'] == 'verified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
