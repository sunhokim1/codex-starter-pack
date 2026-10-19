"""Build/check the complete starter bundle without third-party dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import uuid
import zipfile
from install_sev import bundle_files, verify_bundle
from runtime_safety import reject_links

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.3.3'

# Keep in agreement with the root distribution/manifest.json. Extra files fail
# verify_bundle rather than silently becoming public package inputs.
SOURCE_FILES = (
    'AGENTS.md',
    'CONTINUOUS_IMPROVEMENT.md',
    'README.md',
    'REPAIR_NOTES.md',
    'SKILL.md',
    'assets/project-workflow/SKILL.template.md',
    'assets/runner/PROJECT-WORKFLOW.md',
    'assets/runner/SKILL.template.md',
    'assets/runner/project.py',
    'assets/runner/run.py',
    'assets/runner/runtime_safety.py',
    'assets/runner/workspace.py',
    'assets/sev/requirements.txt',
    'assets/sev/selector.py',
    'assets/sev/setup_model.py',
    'assets/sev/sev-candidate.npz',
    'assets/sev/sev-long-candidate.npz',
    'assets/sev/sev_candidate.py',
    'assets/sev/sev_keyword_selector.py',
    'assets/sev/sev_long_candidate.py',
    'assets/sev/sev_service.py',
    'assets/starter/.ai/config.yaml',
    'assets/starter/.ai/models.yaml',
    'assets/starter/.ai/routing.yaml',
    'assets/starter/.ai/verification.yaml',
    'assets/starter/.gitignore',
    'assets/starter/AGENTS.md',
    'assets/starter/PROJECT.md',
    'assets/starter/README.md',
    'scripts/bootstrap.ps1',
    'scripts/install_sev.py',
    'scripts/package_starter.py',
    'scripts/scaffold.py',
    'tests/test_project_workflow.py',
    'tests/test_regressions.py',
    'tests/test_sandbox_preflight.py',
    'tests/test_workflow_contracts.py',
)


def manifest(root=ROOT):
    files = {name: root/name for name in SOURCE_FILES}
    for path in files.values():
        reject_links(path)
    return {'version': VERSION, 'sha256': {
        'universal-ai-starter/' + name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in sorted(files.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.check:
        verify_bundle(ROOT)
        print('OK: complete file set and SHA256 verified')
        return 0
    destination = reject_links(args.output)
    if destination.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('archive output must be outside the source bundle')
    destination.parent.mkdir(parents=True, exist_ok=True)
    (ROOT/'release.json').write_text(json.dumps(manifest(), indent=2) + '\n', encoding='utf-8')
    verify_bundle(ROOT)
    temp = destination.with_name(destination.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with zipfile.ZipFile(temp, 'x', zipfile.ZIP_DEFLATED) as archive:
            for name, path in sorted(bundle_files(ROOT).items()):
                archive.write(path, 'universal-ai-starter/' + name)
            archive.write(ROOT/'release.json', 'universal-ai-starter/release.json')
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    print('OK: built ' + str(destination))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
