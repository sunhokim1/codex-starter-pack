"""Discover the new inactive 0.4.0 contract fixtures without activating its runtime."""
import importlib.util
from pathlib import Path


def load_tests(loader, tests, pattern):
    source = (Path(__file__).resolve().parents[1] /
              'distribution/releases/0.4.0/universal-ai-starter/tests/test_contracts.py')
    spec = importlib.util.spec_from_file_location('rev_040_test_contracts', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return loader.loadTestsFromModule(module)
