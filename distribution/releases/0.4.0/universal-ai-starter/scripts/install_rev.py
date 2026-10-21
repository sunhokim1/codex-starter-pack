"""Explicit isolated source deployment and connection migration; no downloads or startup."""
import argparse
import base64
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode = True
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'assets'))
from rev import contracts as c
from rev.hardware import diagnose, installation_modes
from rev.selector import Client, validate_ready
from runner.runtime_safety import reject_links
from runner.locking import locked

VERSION = '0.4.0'


def bounded_connection_capacity(info, connection, report):
    """Validate an already warmed bounded service; never turn estimates into proof.

    Connection migration does not start a model. A resident-only estimate cannot
    veto the authenticated bounded mode, but unknown resources still fail closed.
    """
    resources = [report.get(key) for key in ('total_ram_bytes', 'available_ram_bytes')]
    if any(type(value) is not int or value <= 0 for value in resources) or resources[1] > resources[0]:
        raise ValueError('Rev bounded 연결의 현재 RAM probe를 확인할 수 없습니다')
    validate_ready(info, connection)
    plan = info.get('memory_plan', {})
    if not isinstance(plan, dict):
        raise ValueError('Rev bounded 연결의 memory plan이 올바르지 않습니다')
    numbers = [plan.get(key) for key in ('estimated_process_bytes', 'process_budget_bytes', 'safety_margin_bytes',
               'observed_peak_rss_bytes', 'observed_peak_private_bytes')]
    if (info.get('device') != 'cpu' or plan.get('mode') != 'bounded-cpu' or plan.get('device') != 'cpu'
            or plan.get('dtype') != info.get('dtype') or info.get('offload_mode') != 'block-private-mmap'
            or info.get('inference_evidence') != 'official-warmup-completed; authenticated-score-evidence-required'
            or not isinstance(info.get('derived_manifest_sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}', info.get('derived_manifest_sha256', ''))
            or any(type(value) is not int or value <= 0 for value in numbers)
            or type(plan.get('row_token_budget')) is not int or not 1 <= plan['row_token_budget'] <= 16384
            or numbers[2] < 1024**3 or max(numbers[0], numbers[3], numbers[4]) > numbers[1]
            or report.get('available_ram_bytes', 0) < numbers[2]):
        raise ValueError('Rev bounded 연결의 실제 warm/identity/자원 증거가 부족합니다. 외부 watchdog과 현재 RAM을 확인하세요')


def verify_bundle(root):
    root = reject_links(root)
    release = json.loads(reject_links(root / 'release.json').read_text(encoding='utf-8'))
    if release.get('version') != VERSION or not release.get('sha256'):
        raise ValueError('Expected 0.4.0 release manifest')
    expected = set()
    for name, digest in release['sha256'].items():
        if not name.startswith('universal-ai-starter/'):
            raise ValueError('Wrong archive root')
        relative = name[len('universal-ai-starter/'):]
        if '\\' in relative or ':' in relative or any(x in ('', '.', '..') for x in relative.split('/')):
            raise ValueError('Unsafe release path')
        path = reject_links(root / relative)
        c.verify_artifacts(root, {relative: digest})
        expected.add(relative)
    entries = [reject_links(p) for p in root.rglob('*')]
    actual = {p.relative_to(root).as_posix() for p in entries if p.is_file()
              and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name != 'release.json'}
    if actual != expected:
        raise ValueError('Bundle contains missing or unmanifested files')
    return VERSION


def reference_report(projects, legacy_runtime=None):
    """Only explicitly supplied roots; cannot establish global non-use."""
    result = dict(scope='explicit_project_roots_only', exhaustive=False, deletion_allowed=False,
                  checked=0, legacy_references=0, unreadable=0, other_legacy_references=0)
    for project in projects:
        result['checked'] += 1
        try:
            path = reject_links(Path(project) / '.ai/sev.json')
            if path.exists():
                value = json.loads(path.read_text(encoding='utf-8-sig'))
                if legacy_runtime is None or value.get('deployment') == str(legacy_runtime):
                    result['legacy_references'] += 1
                else:
                    result['other_legacy_references'] += 1
        except (OSError, ValueError):
            result['unreadable'] += 1
    return result


def inspect(project):
    project = reject_links(project)
    legacy = (project / '.ai/sev.json').exists()
    states = [name for name in ('.ai/project-workflow/state.json', '.ai/rev-workflow/state.json')
              if reject_links(project / name).exists()]
    return dict(legacy_connection=legacy, state_files=states,
                action='Preserve full reports; review/archive incompatible state explicitly; completed tasks must never replay',
                references=reference_report([project]))


def managed_block(original, begin, end, block, legacy=None):
    """Replace only a complete known managed block; preserve all other bytes."""
    pairs=[(begin,end)]+([legacy] if legacy else [])
    found=[]
    for first,last in pairs:
        if original.count(first)!=original.count(last) or original.count(first)>1:
            raise ValueError('Ambiguous managed guidance; review manually before migration')
        if first in original:
            start=original.index(first);finish=original.index(last)+len(last)
            if original.index(last)<start:raise ValueError('Invalid managed guidance order')
            found.append((start,finish))
    if len(found)>1:raise ValueError('Multiple managed guidance versions; reconcile explicitly')
    if found:
        start,finish=found[0]
        return original[:start]+block+original[finish:]
    return original+('' if not original or original.endswith('\n') else '\n')+'\n'+block+'\n'


def guidance_updates(project):
    guidance='<!-- starter-rev:start -->\n## Rev 0.4.0 순차 실행\n.ai/rev-install.json의 python·runner·project_runner 경로와 .ai/rev.json 연결을 사용한다. 새 요청에 기존 SEV 연결이나 개인 SEV skill을 사용하지 않는다. 큰 목표는 Sol 계획 후 각 구현을 Rev로 선택하고, 작은 요청은 직접 Rev로 선택한다. 명시적 실행 override는 Rev를 우회한다. 앱 대화 모델은 변경되지 않는다. Python controller의 승인·예산·실제 검증·재개 경계를 유지한다. 구 상태와 완료 작업을 자동 재실행하지 않는다.\n<!-- starter-rev:end -->'
    ignore='# starter-rev-private:start\n.ai/rev.json\n.ai/rev-install.json\n.ai/rev-workflow/\n.ai/reports/\n.ai/installation.lock\n# starter-rev-private:end'
    updates=[]
    for name,first,last,block,legacy in (
        ('AGENTS.md','<!-- starter-rev:start -->','<!-- starter-rev:end -->',guidance,
         ('<!-- starter-sev:start -->','<!-- starter-sev:end -->')),
        ('.gitignore','# starter-rev-private:start','# starter-rev-private:end',ignore,None)):
        path=reject_links(project/name)
        before=path.read_bytes() if path.exists() else None
        original=(before or b'').decode('utf-8')
        after=managed_block(original,first,last,block,legacy).encode('utf-8')
        updates.append((path,before,after))
    return updates


def replace_document(path, before, after):
    if (path.read_bytes() if path.exists() else None)!=before:
        raise ValueError('Concurrent document edit; preserve state and reconcile manually')
    temp=reject_links(path.with_name(path.name+'.rev-'+uuid.uuid4().hex+'.tmp'))
    try:
        with temp.open('xb') as stream:
            stream.write(after);stream.flush();os.fsync(stream.fileno())
        reject_links(path)
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)


def deploy(bundle, project, runtime, connection, *, migrate=False, ready=None, hardware=None):
    """Injectable readiness/hardware for offline fixtures; CLI has no bypass flags."""
    bundle, project, runtime = map(reject_links, (bundle, project, runtime))
    if project == Path(project.anchor) or not project.is_dir():
        raise ValueError('Select an existing project directory, not a drive root')
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a)
           for a, b in ((project, runtime), (bundle, runtime))):
        raise ValueError('Runtime must be separate from project and bundle')
    if runtime.exists():
        raise ValueError('Runtime destination exists; use a new isolated directory')
    verify_bundle(bundle)
    c.validate_connection(connection)
    expected = hashlib.sha256((bundle / 'contracts/upstream.lock.json').read_bytes()).hexdigest()
    if connection['lock_sha256'] != expected:
        raise ValueError('Connection supply-chain identity differs from bundle')
    report = inspect(project)
    if report['state_files']:
        raise ValueError('Preserve/review/archive existing state explicitly before connecting; never replay completed tasks')
    if report['legacy_connection'] and not migrate:
        raise ValueError('Existing SEV requires explicit --migrate; shared SEV will be preserved')
    dest = reject_links(project / '.ai/rev.json')
    metadata = reject_links(project / '.ai/rev-install.json')
    if dest.exists() or metadata.exists():
        raise ValueError('Existing Rev connection preserved; explicitly archive/reconcile before reconnecting')
    resources = (hardware or diagnose)()
    resident_candidate = bool(installation_modes(resources)['modes'])
    if not resident_candidate and any(type(resources.get(key)) is not int or resources[key] <= 0
                                     for key in ('total_ram_bytes', 'available_ram_bytes')):
        raise ValueError('Rev 준비 필요: 메모리 추정에 필요한 probe 미확인입니다. 소스 설치·업데이트는 별도로 가능합니다')
    info = (ready or (lambda value: Client(value).ready()))(connection)
    if not resident_candidate:
        bounded_connection_capacity(info, connection, resources)
    # Reject legacy settings rather than overwrite user choices. Review conversion separately.
    from runner.controller import configuration
    configuration(project)
    updates = guidance_updates(project)
    stage = runtime.with_name(runtime.name + '.stage-' + uuid.uuid4().hex)
    created = []
    updated = []
    published_runtime = False
    runtime.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(bundle, stage, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        verify_bundle(stage)
        os.rename(stage, runtime)
        published_runtime = True
        payloads = ((dest, connection), (metadata, dict(version=VERSION, deployment=str(runtime),
                    python=str(Path(sys.executable).absolute()),
                    runner=str(runtime/'assets/runner/run.py'),
                    project_runner=str(runtime/'assets/runner/project.py'))))
        for path, value in payloads:
            reject_links(path)
            with path.open('x', encoding='utf-8') as stream:
                created.append(path)
                json.dump(value, stream, ensure_ascii=False, indent=2)
        for path,before,after in updates:
            replace_document(path,before,after)
            updated.append((path,before,after))
        return dict(status='connected', version=VERSION, legacy_preserved=True,
                    references=report['references'], inference_measured=False)
    except BaseException:
        conflict=False
        for path,before,after in reversed(updated):
            if path.read_bytes()!=after:
                conflict=True
                continue
            if before is None:path.unlink()
            else:replace_document(path,after,before)
        for path in reversed(created):
            path.unlink(missing_ok=True)
        if published_runtime:
            # Only the exact new directory published by this transaction is owned here.
            reject_links(runtime)
            shutil.rmtree(runtime)
        if conflict:raise ValueError('Concurrent migration edits preserved; manually reconcile guidance before retry')
        raise
    finally:
        if stage.exists():
            reject_links(stage)
            shutil.rmtree(stage)


# Source ownership is project-local. It never changes execution references or guidance.
SOURCE_RECEIPT = '.ai/source-install.json'
SOURCE_ROOT = '.ai/starter-source/'


def source_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', name) or any(
            x in ('', '.', '..') or x.endswith((' ', '.')) or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', x, re.I) for x in name.split('/')):
        raise ValueError('Unsafe source receipt path')
    if name != SOURCE_RECEIPT and not name.startswith(SOURCE_ROOT) and name not in (
            'AGENTS.md', 'PROJECT.md', 'README.md', '.gitignore', '.ai/config.yaml',
            '.ai/models.yaml', '.ai/routing.yaml', '.ai/verification.yaml'):
        raise ValueError('Unowned source path')
    return name


@contextmanager
def source_locks(project):
    # Same byte-lock boundaries as the manager; no workflow state is rewritten.
    with ExitStack() as stack:
        for name in ('.ai/installation.lock', '.ai/project-workflow/lock', '.ai/rev-workflow/lock'):
            path = reject_links(project / name)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_nlink != 1:
                raise ValueError('Aliased source lock; review required')
            stream = stack.enter_context(path.open('a+b'))
            stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def source_idle(project):
    for name in ('.ai/project-workflow/state.json', '.ai/rev-workflow/state.json'):
        path = reject_links(project / name)
        if path.exists() and json.loads(path.read_text(encoding='utf-8-sig')).get('status') != 'completed':
            raise ValueError('Active or uncertain workflow; review before source update')
    reports = reject_links(project / '.ai/reports')
    if reports.exists():
        for path in reports.rglob('*.json'):
            if json.loads(reject_links(path).read_text(encoding='utf-8-sig')).get('status') == 'running':
                raise ValueError('Active or uncertain execution report')


def source_install(bundle, project, snapshot=None):
    """Bounded write-ahead before/after images; existing user files are adoption-only.

    Caller holds source_locks (or manager stage isolation). No model or service probe.
    """
    bundle, project = map(reject_links, (bundle, project))
    if project == Path(project.anchor) or not project.is_dir():
        raise ValueError('Select an existing project directory')
    verify_bundle(bundle)
    source_idle(project)
    journal = reject_links(project / '.ai/source-transaction.json')
    if journal.exists():
        recover_source(project)
    receipt_path = reject_links(project / SOURCE_RECEIPT)
    previous = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else None
    release = json.loads((bundle / 'release.json').read_text(encoding='utf-8'))
    def version(value):
        import re
        if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
            raise ValueError('Unknown source version')
        return tuple(map(int, value.split('.')))
    if previous:
        if version(previous.get('version')) > version(VERSION):
            return dict(source_status='newer', changed=False, rev_status='preparation_needed', version=previous['version'])
        if previous.get('schema') != 1 or not isinstance(previous.get('sha256'), dict):
            raise ValueError('Invalid source receipt')
        for name, digest in previous['sha256'].items():
            if not source_name(name).startswith(SOURCE_ROOT):
                raise ValueError('Invalid managed source ownership')
            path = reject_links(project / name)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Modified or missing managed source; review required')
        prior_release = reject_links(project / (SOURCE_ROOT + 'release.json'))
        if not prior_release.is_file():
            raise ValueError('Missing source release metadata')
        prior_release = json.loads(prior_release.read_text(encoding='utf-8'))
        recorded = {SOURCE_ROOT + name.split('/', 1)[1]: digest
                    for name, digest in prior_release.get('sha256', {}).items()
                    if name.startswith('universal-ai-starter/')}
        if prior_release.get('version') != previous['version'] or recorded != {
                name: digest for name, digest in previous['sha256'].items()
                if name != SOURCE_ROOT + 'release.json'} or SOURCE_ROOT + 'release.json' not in previous['sha256']:
            raise ValueError('Source receipt and release metadata differ')
    elif reject_links(project / SOURCE_ROOT).exists():
        raise ValueError('Unreceipted source tree; review required')
    payloads = {SOURCE_ROOT + name.split('/', 1)[1]: (bundle / name.split('/', 1)[1]).read_bytes()
                for name in release['sha256']}
    payloads[SOURCE_ROOT + 'release.json'] = (bundle / 'release.json').read_bytes()
    if previous and set(previous['sha256']) != set(payloads):
        # Additions are safe; removals require review rather than retain stale executable code.
        if set(previous['sha256']) - set(payloads):
            raise ValueError('Removed managed source paths require explicit review')
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    owned = reject_links(project / SOURCE_ROOT)
    if owned.exists():
        actual = {reject_links(p).relative_to(project).as_posix() for p in owned.rglob('*') if p.is_file()}
        if actual != set(previous['sha256']):
            raise ValueError('Unknown managed source files; review required')
    for path in (bundle / 'assets/starter').rglob('*'):
        if path.is_file():
            name = path.relative_to(bundle / 'assets/starter').as_posix()
            if not reject_links(project / name).exists():
                payloads[source_name(name)] = path.read_bytes()
    receipt = dict(schema=1, version=VERSION, snapshot=snapshot, sha256=hashes,
                   execution_connected=False)
    payloads[SOURCE_RECEIPT] = (json.dumps(receipt, sort_keys=True, indent=2)+'\n').encode()
    entries = []
    for name, after in payloads.items():
        path = reject_links(project / source_name(name))
        before = path.read_bytes() if path.exists() else None
        if before != after:
            entries.append(dict(name=name, before=None if before is None else base64.b64encode(before).decode(),
                                after=base64.b64encode(after).decode()))
    if entries:
        journal.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(dict(schema=1, entries=entries)).encode()
        if len(encoded) > 16*1024*1024:
            raise ValueError('Source transaction exceeds bounded journal size')
        replace_document(journal, None, encoded)
        try:
            for entry in entries:
                source_idle(project)
                path = reject_links(project / entry['name']); path.parent.mkdir(parents=True, exist_ok=True)
                replace_document(path, None if entry['before'] is None else base64.b64decode(entry['before']),
                                 base64.b64decode(entry['after']))
        except BaseException:
            recover_source(project)
            raise
        # Completion marker: recovery after this durable write retains the complete publication.
        replace_document(journal, encoded, json.dumps(dict(schema=1, committed=True, entries=entries)).encode())
        journal.unlink()
    return dict(source_status='installed' if entries else 'current', changed=bool(entries),
                version=VERSION, rev_status='preparation_needed', inference_measured=False)


def recover_source(project):
    journal = reject_links(project / '.ai/source-transaction.json')
    if journal.stat().st_size > 16*1024*1024:
        raise ValueError('Oversized source journal; review required')
    state = json.loads(journal.read_text(encoding='utf-8'))
    if state.get('schema') != 1 or not isinstance(state.get('entries'), list) or len(state['entries']) > 520:
        raise ValueError('Ambiguous source journal; review required')
    if set(state) - {'schema', 'entries', 'committed'} or ('committed' in state and state['committed'] is not True):
        raise ValueError('Ambiguous source journal phase')
    entries = state['entries']
    if any(not isinstance(e, dict) or set(e) != {'name', 'before', 'after'} for e in entries):
        raise ValueError('Ambiguous source journal entries')
    if len({e['name'] for e in entries}) != len(entries):
        raise ValueError('Duplicate source journal paths')
    decoded = []
    for entry in entries:
        path = reject_links(project / source_name(entry['name']))
        before = None if entry['before'] is None else base64.b64decode(entry['before'], validate=True)
        after = base64.b64decode(entry['after'], validate=True)
        current = path.read_bytes() if path.exists() else None
        if current not in (before, after) or (state.get('committed') and current != after):
            raise ValueError('Concurrent source edit; journal preserved for review')
        decoded.append((path, before, after))
    if not state.get('committed'):
        for path, before, after in reversed(decoded):
            current = path.read_bytes() if path.exists() else None
            if current == before: continue
            if current != after:
                raise ValueError('Concurrent edit during source recovery')
            if before is None:
                path.unlink()
                parent = path.parent
                while parent != project:
                    if any(parent.iterdir()): break
                    parent.rmdir(); parent = parent.parent
            else: replace_document(path, after, before)
    journal.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path)
    parser.add_argument('--connection-file', type=Path)
    parser.add_argument('--migrate', action='store_true')
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--snapshot')
    parser.add_argument('--no-autostart', action='store_true', help='compatibility: startup is never registered')
    args = parser.parse_args(argv)
    try:
        if args.plan:
            print(json.dumps(inspect(args.target), ensure_ascii=True))
            return 0
        if args.source_only:
            with source_locks(reject_links(args.target)):
                result = source_install(Path(__file__).resolve().parents[1], args.target, args.snapshot)
            print(json.dumps(result, ensure_ascii=True))
            return 0
        if not args.runtime_root or not args.connection_file:
            raise ValueError('Connection preparation requires explicit --runtime-root and --connection-file; inspect --plan first. Use --source-only for automatic source/client installation without Rev readiness')
        connection = json.loads(reject_links(args.connection_file).read_text(encoding='utf-8-sig'))
        with locked(reject_links(args.target)):
            result = deploy(Path(__file__).resolve().parents[1], args.target, args.runtime_root,
                            connection, migrate=args.migrate)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        # Errors are static; do not serialize connection content, tokens or private paths.
        print('Rev connection stopped. Inspect hardware, manifest, settings and --plan; preserve existing state. ' +
              (str(error) if isinstance(error, ValueError) else 'Filesystem operation failed'), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
