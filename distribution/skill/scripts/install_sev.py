"""Install one shared local SEV runtime and connect a project, without replacing facts."""
import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

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
{END}'''


def merge_guidance(text):
    if BEGIN in text:
        if END not in text or text.count(BEGIN) != 1 or text.count(END) != 1:
            raise ValueError('ambiguous SEV instruction markers')
        start, tail = text.split(BEGIN, 1)
        _, rest = tail.split(END, 1)
        return start + project_guidance() + rest
    return text.rstrip() + '\n\n' + project_guidance() + '\n'


def checked(command):
    subprocess.run([str(x) for x in command], check=True)


def verify_bundle(bundle):
    release = json.loads((bundle/'release.json').read_text(encoding='utf-8'))
    if release.get('version') != '0.3.0' or not release.get('sha256'):
        raise ValueError('unexpected or empty starter release')
    for name, digest in release['sha256'].items():
        if (not isinstance(name, str) or not name.startswith('universal-ai-starter/')
                or '\\' in name or ':' in name
                or any(p in ('', '.', '..') for p in name.split('/'))
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('unsafe release path or hash')
        relative = Path(*name.split('/')[1:])
        if '..' in relative.parts or relative.is_absolute():
            raise ValueError('unsafe release path')
        path = bundle/relative
        if not path.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('release path escaped bundle')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('bundle integrity check failed: ' + str(relative))
    return release['version']


def validate_project_paths(target):
    # Reject links/junctions before any runtime or project writes.
    for leaf in (target/'AGENTS.md', target/'.ai/models.yaml', target/'.ai/sev.json'):
        for path in (leaf, *leaf.parents):
            if path.is_symlink() or (path.exists() and
                    getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
                raise ValueError('project path contains a link or reparse point: ' + str(path))
        if leaf.exists() and not leaf.is_file():
            raise ValueError('project file path is not a file: ' + str(leaf))


def install(target, runtime, skills, bundle, model_source=None, autostart=True):
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11 or newer is required')
    validate_project_paths(Path(target).absolute())
    target, runtime, skills, bundle = map(lambda p: Path(p).resolve(), (target,runtime,skills,bundle))
    version = verify_bundle(bundle)
    if not (target/'AGENTS.md').is_file() or not (target/'.ai/models.yaml').is_file():
        raise ValueError('apply/merge starter core files before installing SEV')
    # Validate the merge before installing anything; preserve all non-managed content.
    agents = merge_guidance((target/'AGENTS.md').read_text(encoding='utf-8'))
    runtime.mkdir(parents=True, exist_ok=True)
    state = runtime/'service.json'
    python = runtime/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    service = runtime/'sev_service.py'
    if state.exists() and python.exists() and service.exists():
        checked([python,service,'stop','--state',state])
    for original in (bundle/'assets/sev').iterdir():
        if original.is_file(): shutil.copy2(original,runtime/original.name)
    if not python.exists(): checked([sys.executable,'-m','venv',runtime/'venv'])
    checked([python,'-m','pip','install','--disable-pip-version-check','-r',runtime/'requirements.txt'])
    if model_source:
        shutil.copytree(Path(model_source).resolve(),runtime/'model',dirs_exist_ok=True)
    checked([python,runtime/'setup_model.py'])
    runner = skills/'single-model-runner'
    (runner/'scripts').mkdir(parents=True,exist_ok=True)
    shutil.copy2(bundle/'assets/runner/run.py',runner/'scripts/run.py')
    shutil.copy2(bundle/'assets/runner/SKILL.template.md',runner/'SKILL.md')
    config = {'version':version,'python':str(python),'service':str(service),'state':str(state),
              'runner':str(runner/'scripts/run.py'),'skills':str(skills)}
    # Service preparation must succeed before enabling the project's development flow.
    checked([python,service,'start','--state',state])
    startup = None
    if autostart and os.name=='nt':
        startup = Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup/SEV Local Selector.lnk'
        pythonw = python.with_name('pythonw.exe')
        def quote(value): return "'" + str(value).replace("'", "''") + "'"
        arguments = f'"{service}" start --state "{state}"'
        script = ("$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'; $s=New-Object -ComObject WScript.Shell; "
            f'$l=$s.CreateShortcut({quote(startup)});$l.TargetPath={quote(pythonw)};'
            f'$l.Arguments={quote(arguments)};$l.WorkingDirectory={quote(runtime)};'
            '$l.WindowStyle=7;$l.Save()')
        encoded = base64.b64encode(script.encode('utf-16-le')).decode()
        checked(['powershell.exe','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',encoded])
    (target/'.ai/sev.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (target/'AGENTS.md').write_text(agents,encoding='utf-8')
    print(json.dumps({'installed':True,'version':version,'runtime':str(runtime),
        'project':str(target),'autostart':str(startup) if startup else None,
        'classification_api_calls':0,'app_chat_model_changed':False}))


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
