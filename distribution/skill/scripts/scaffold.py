"""Copy the bundled starter with complete conflict preflight and no overwrites."""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'assets' / 'starter'
    target = Path(args.target).expanduser().resolve()
    files = sorted(p for p in source.rglob('*') if p.is_file())
    if len(files) != 27:
        print('ERROR: template must contain exactly 27 files.', file=sys.stderr)
        return 2
    if target.exists() and not target.is_dir():
        print('ERROR: target is not a directory.', file=sys.stderr)
        return 2
    conflicts = []
    for original in files:
        dest = target / original.relative_to(source)
        if dest.exists() or dest.is_symlink():
            conflicts.append(str(dest))
        parent = dest.parent
        while parent != target:
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                conflicts.append(str(parent))
            parent = parent.parent
        if not dest.resolve().is_relative_to(target):
            conflicts.append(str(dest))
    if conflicts:
        print('ERROR: conflicts detected; no files written:', file=sys.stderr)
        for path in sorted(set(conflicts)):
            print(path, file=sys.stderr)
        return 2
    if args.dry_run:
        print(f'OK: would create {len(files)} files in {target}')
        return 0
    for original in files:
        dest = target / original.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as output:
            output.write(original.read_bytes())
    print(f'OK: created {len(files)} files in {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
