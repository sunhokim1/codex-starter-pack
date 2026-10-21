"""Rev 0.4.0 compatibility import. Legacy classifier APIs are intentionally incompatible."""
import sys
from pathlib import Path
_bundle = Path(__file__).resolve().parents[2] / 'distribution/releases/0.4.0/universal-ai-starter/assets'
sys.path.insert(0, str(_bundle))
from rev.selector import Client, select
