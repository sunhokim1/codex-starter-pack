"""Install one shared local SEV runtime and connect a project, without replacing facts."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets/runner"))
from runtime_safety import private_write, redact, reject_links

BEGIN = '<!-- starter-sev:start -->'
END = '<!-- starter-sev:end -->'


def project_guidance():
    return f'''{BEGIN}
## Local SEV execution

When `.ai/sev.json` exists, use the installed `single-model-runner` for development
requests without requiring the user to name the skill. Read the paths from that JSON.
Pass the request and already known project facts unchanged. Use --model worker|main
for a user override; otherwise use persistent SEV. General questions stay in this chat.
The selected model owns implementation and verification; do not repeat its work.
Do not invoke the runner again inside a task it already selected. No subagents or
parallel agents. This authorized local workflow takes precedence over manual selection
guidance. On service failure stop and report; never substitute a paid classifier.
The app chat model does not change. This is instruction-based invocation, not interception.

For project-sized development goals that require multiple implementation steps,
milestones or cross-subsystem changes, automatically use the installed `project-workflow`
skill (project_runner in .ai/sev.json). The user gives the goal once; do not require a
special phrase or individual subtask prompts. It plans once, then calls the single-task
runner sequentially from its outer controller, persists progress and runs configured
checks. Never invoke it inside an already selected task. Ordinary questions and small
contained requests retain the existing quick path. Honor approval, failure and budget
stops; never silently retry interrupted work or extend budgets.
{END}'''


def merge_guidance(text):
    if BEGIN in text or END in text:
        if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) >= text.index(END):
            raise ValueError('ambiguous SEV instruction markers')
        start, tail = text.split(BEGIN, 1)
        _, rest = tail.split(END, 1)
        return start + project_guidance() + rest
    return text.rstrip() + '\n\n' + project_guidance() + '\n'


def checked(command):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                            encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError('installation step failed: ' + redact((result.stdout + result.stderr)[-4000:]))


def bundle_files(bundle):
    return {p.relative_to(bundle).as_posix(): p for p in bundle.rglob('*')
            if p.is_file() and p.name != 'release.json' and p.suffix != '.pyc'
            and not any(part in ('__pycache__', '.git') for part in p.relative_to(bundle).parts)}


def verify_bundle(bundle):
    bundle = reject_links(bundle)
    release = json.loads((bundle/'release.json').read_text(encoding='utf-8'))
    if release.get('version') != '0.3.1' or not isinstance(release.get('sha256'), dict) or not release['sha256']:
        raise ValueError('unexpected or empty starter release')
    actual = bundle_files(bundle)
    expected = set()
    for name, digest in release['sha256'].items():
        if (not isinstance(name, str) or not name.startswith('universal-ai-starter/')
                or chr(92) in name or ':' in name
                or any(p in ('', '.', '..') for p in name.split('/'))
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('unsafe release path or hash')
        relative = '/'.join(name.split('/')[1:])
        expected.add(relative)
        path = reject_links(bundle/relative)
        if not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('release path escaped bundle')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('bundle integrity check failed: ' + relative)
    if set(actual) != expected:
        raise ValueError('bundle contains missing or unlisted files')
    # Never copy directory enumeration or bytecode caches into the runtime.
    for path in actual.values():
        reject_links(path)
    return release['version']


@contextmanager
def installation_lock(path):
    path = reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('another installation is active') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


IGNORE_BEGIN = '# starter-private:start'
IGNORE_END = '# starter-private:end'
IGNORE_RULES = ['.ai/sev.json', '.ai/project-workflow/', '.ai/reports/', '.ai/installation.lock', '.env', '.env.*', '!.env.example']


def merge_ignore(text):
    block = IGNORE_BEGIN + '\n' + '\n'.join(IGNORE_RULES) + '\n' + IGNORE_END
    if IGNORE_BEGIN in text or IGNORE_END in text:
        if (text.count(IGNORE_BEGIN) != 1 or text.count(IGNORE_END) != 1
                or text.index(IGNORE_BEGIN) >= text.index(IGNORE_END)):
            raise ValueError('ambiguous private ignore markers')
        start, tail = text.split(IGNORE_BEGIN, 1)
        _, rest = tail.split(IGNORE_END, 1)
        return start + block + rest
    return text.rstrip() + '\n\n' + block + '\n'


def startup_path(deployment):
    if os.name != 'nt':
        return None
    return reject_links(Path(os.environ['APPDATA'])/
        'Microsoft/Windows/Start Menu/Programs/Startup'/('SEV Local Selector ' + deployment.name + '.lnk'))


def create_startup(path, python, service, state, deployment):
    def quote(value): return "'" + str(value).replace("'", "''") + "'"
    arguments = f'"{service}" start --state "{state}"'
    script = ("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'; $s=New-Object -ComObject WScript.Shell; "
        f'$l=$s.CreateShortcut({quote(path)});$l.TargetPath={quote(python.with_name("pythonw.exe"))};'
        f'$l.Arguments={quote(arguments)};$l.WorkingDirectory={quote(deployment)};'
        '$l.WindowStyle=7;$l.Save()')
    encoded = base64.b64encode(script.encode('utf-16-le')).decode()
    checked(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',encoded])


def validate_project_paths(target):
    # Reject links/junctions before any runtime or project writes.
    for leaf in (target/'AGENTS.md', target/'.ai/models.yaml', target/'.ai/sev.json', target/'.gitignore'):
        for path in (leaf, *leaf.parents):
            if path.is_symlink() or (path.exists() and
                    getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('project path contains a link or reparse point: ' + str(path))
        if leaf.exists() and not leaf.is_file():
            raise ValueError('project file path is not a file: ' + str(leaf))


def install(target, runtime, skills, bundle, model_source=None, autostart=True):
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11 or newer is required')
    target, runtime, skills, bundle = map(reject_links, (target, runtime, skills, bundle))
    validate_project_paths(target)
    version = verify_bundle(bundle)
    if not (target/'AGENTS.md').is_file() or not (target/'.ai/models.yaml').is_file():
        raise ValueError('apply/merge starter core files before installing SEV')
    with installation_lock(runtime/'installation.lock'), installation_lock(target/'.ai/installation.lock'):
        return install_locked(target, runtime, skills, bundle, version, model_source, autostart)


def install_locked(target, runtime, skills, bundle, version, model_source, autostart):
    agents = merge_guidance((target/'AGENTS.md').read_text(encoding='utf-8'))
    ignore_path = target/'.gitignore'
    ignore = merge_ignore(ignore_path.read_text(encoding='utf-8') if ignore_path.exists() else '')
    # Each deployment is immutable for existing projects. A failed/new install never
    # stops the old service or overwrites its venv, runtime, runner or user skills.
    deployment = runtime/'releases'/(version + '-' + uuid.uuid4().hex)
    deployment.mkdir(parents=True)
    state = deployment/'service.json'
    python = deployment/'venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    service = deployment/'sev_service.py'
    runner = deployment/'runner'
    created = []
    snapshots = {}
    start_attempted = False
    startup = startup_path(deployment) if autostart else None
    try:
        for relative in bundle_files(bundle):
            if relative.startswith('assets/sev/'):
                original = bundle/relative
                dest = deployment/original.relative_to(bundle/'assets/sev')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, dest)
        shutil.copy2(bundle/'assets/runner/runtime_safety.py', deployment/'runtime_safety.py')
        shutil.copytree(bundle/'assets/runner', runner, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        checked([sys.executable, '-m', 'venv', deployment/'venv'])
        checked([python, '-m', 'pip', 'install', '--disable-pip-version-check', '-r', deployment/'requirements.txt'])
        if model_source:
            model_source = reject_links(model_source)
            for name in ('onnx/model_quint8_avx2.onnx', 'tokenizer.json', 'tokenizer_config.json', 'config.json'):
                original = reject_links(model_source/name)
                dest = deployment/'model'/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, dest)
        checked([python, deployment/'setup_model.py'])
        start_attempted = True
        checked([python, service, 'start', '--state', state])
        # Verify readiness independently of the start command's exit status.
        checked([python, service, 'status', '--state', state])
        skill_files = {
            skills/'single-model-runner/SKILL.md': bundle/'assets/runner/SKILL.template.md',
            skills/'single-model-runner/PROJECT-WORKFLOW.md': bundle/'assets/runner/PROJECT-WORKFLOW.md',
            skills/'project-workflow/SKILL.md': bundle/'assets/project-workflow/SKILL.template.md',
        }
        preserved = []
        for dest, original in skill_files.items():
            reject_links(dest)
            if dest.exists():
                if not dest.is_file(): raise ValueError('skill destination is not a file')
                preserved.append(str(dest))
            else:
                created.append(dest)
                private_write(dest, original.read_bytes())
        config = {'version': version, 'python': str(python), 'service': str(service), 'state': str(state),
                  'runner': str(runner/'run.py'), 'project_runner': str(runner/'project.py'),
                  'skills': str(skills), 'deployment': str(deployment)}
        changes = {ignore_path: ignore, target/'AGENTS.md': agents,
                   target/'.ai/sev.json': json.dumps(config, ensure_ascii=False, indent=2) + '\n'}
        for dest, data in changes.items():
            reject_links(dest)
            snapshots[dest] = dest.read_bytes() if dest.exists() else None
            private_write(dest, data)
        if startup:
            reject_links(startup)
            if startup.exists(): raise ValueError('new startup path unexpectedly exists')
            created.append(startup)
            create_startup(startup, python, service, state, deployment)
        print(json.dumps({'installed': True, 'version': version, 'runtime': str(deployment),
            'project': str(target), 'autostart': str(startup) if startup else None,
            'preserved_skills': preserved, 'classification_api_calls': 0, 'app_chat_model_changed': False}))
        return config
    except BaseException as original_error:
        rollback_errors = []
        for dest, data in reversed(list(snapshots.items())):
            try:
                if data is None: dest.unlink(missing_ok=True)
                else: private_write(dest, data)
            except Exception: rollback_errors.append('project file restoration failed')
        for dest in reversed(created):
            try: reject_links(dest).unlink(missing_ok=True)
            except Exception: rollback_errors.append('new file removal failed')
        if start_attempted:
            try: checked([python, service, 'stop', '--state', state])
            except Exception: rollback_errors.append('new service stop needs inspection')
        # Keep failed deployment for inspection; never recursively delete a venv here.
        detail = '; '.join(rollback_errors) if rollback_errors else 'project files restored; old runtime untouched'
        raise RuntimeError('SEV installation failed; ' + detail + '; inspect deployment ' + str(deployment)) from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',required=True)
    parser.add_argument('--runtime',default=str(Path.home()/'.codex/sev'))
    parser.add_argument('--skills',default=str(Path.home()/'.agents/skills'))
    parser.add_argument('--model-source',help='reuse already downloaded model files (still verified)')
    parser.add_argument('--no-autostart',action='store_true')
    args=parser.parse_args()
    install(args.target,args.runtime,args.skills,Path(__file__).resolve().parents[1],
            args.model_source,not args.no_autostart)


if __name__=='__main__': main()
