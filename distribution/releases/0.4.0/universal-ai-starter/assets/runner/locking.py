"""Sequential workflow lock; copied from the maintained lifecycle primitive."""
import os
from contextlib import contextmanager

@contextmanager
def locked(project):
    directory = project / '.ai/rev-workflow'
    # Do not write workflow state through links/junctions outside the project.
    for path in (project / '.ai', directory):
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('workflow directory must not be a link or reparse point')
    directory.mkdir(parents=True, exist_ok=True)
    for leaf in ('lock', 'state.json'):
        path = directory / leaf
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('workflow file must not be a link or reparse point')
    with (directory / 'lock').open('a+b') as stream:
        stream.seek(0)
        stream.write(b'0')
        stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('another project workflow is active') from error
        try:
            yield directory / 'state.json'
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
