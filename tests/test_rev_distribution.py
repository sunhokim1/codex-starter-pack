"""0.4.0 설치 계약 fixture 검색."""
import importlib.util
from pathlib import Path

def load_tests(loader,tests,pattern):
    path=Path(__file__).resolve().parents[1]/'distribution/releases/0.4.0/universal-ai-starter/tests/test_distribution.py'
    spec=importlib.util.spec_from_file_location('rev040_distribution_tests',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return loader.loadTestsFromModule(module)
