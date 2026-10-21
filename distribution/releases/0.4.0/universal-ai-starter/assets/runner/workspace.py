"""Content fingerprints for resume checks; no file content is stored."""
import hashlib
import os
from pathlib import Path

IGNORED_DIRS = {'.git', '.hg', '.svn', 'node_modules', '.venv', 'venv',
                '__pycache__', '.sev-runtime', '.rev-runtime'}
PRIVATE_AREAS = {'.ai/project-workflow', '.ai/rev-workflow', '.ai/reports'}


def snapshot(project):
    project = Path(project)
    files = {}
    for directory, dirs, names in os.walk(project, followlinks=False):
        base = Path(directory)
        for name in list(dirs):
            path = base/name
            relative = path.relative_to(project).as_posix()
            if name in IGNORED_DIRS or relative in PRIVATE_AREAS:
                dirs.remove(name)
            elif path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                dirs.remove(name)
                files[relative] = 'link:' + hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
        for name in sorted(names):
            path = base/name
            relative = path.relative_to(project).as_posix()
            if (name.endswith('.pyc') or name == '.env' or
                    (name.startswith('.env.') and name != '.env.example') or
                    relative == '.ai/installation.lock'):
                continue
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                files[relative] = 'link:' + hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
            else:
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b''):
                        digest.update(chunk)
                files[relative] = digest.hexdigest()
    return files


def changes(before, after):
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
