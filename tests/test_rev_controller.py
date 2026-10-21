"""Discover 0.4.0 controller contract fixtures, without CLI/model/network calls."""
import importlib.util
from pathlib import Path


def load_tests(loader, tests, pattern):
    path = Path(__file__).resolve().parents[1] / 'distribution/releases/0.4.0/universal-ai-starter/tests/test_controller.py'
    spec = importlib.util.spec_from_file_location('rev040_controller_tests', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return loader.loadTestsFromModule(module)
