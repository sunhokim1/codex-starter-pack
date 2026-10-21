"""Small request entry: no planning call, one local Rev selection unless overridden."""
if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runner.cli import main
else:
    from .cli import main

if __name__ == '__main__':
    raise SystemExit(main(quick=True))
