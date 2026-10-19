"""Compatibility entry point; maintained source is the versioned release bundle."""
import sys
from pathlib import Path
_bundle = Path(__file__).resolve().parents[3] / "distribution/releases/0.3.1/universal-ai-starter"
_entry = _bundle / "assets/runner/run.py"
sys.path.insert(0, str(_bundle / "assets/runner"))
sys.path.insert(0, str(_bundle / "scripts"))
__file__ = str(_entry)
exec(compile(_entry.read_text(encoding="utf-8"), str(_entry), "exec"), globals())
