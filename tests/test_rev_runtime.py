"""Discover offline 0.4.0 runtime fixtures; no downloads, paid calls or real inference."""
import importlib.util
from pathlib import Path


def load_tests(loader, tests, pattern):
    source = Path(__file__).resolve().parents[1] / 'distribution/releases/0.4.0/universal-ai-starter/tests/test_runtime.py'
    spec = importlib.util.spec_from_file_location('rev040_runtime_tests', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return loader.loadTestsFromModule(module)
