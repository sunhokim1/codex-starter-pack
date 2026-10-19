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
VERSION = '0.3.1'


def manifest(root=ROOT):
    files = bundle_files(root)
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
