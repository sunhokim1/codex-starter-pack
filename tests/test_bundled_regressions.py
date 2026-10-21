"""controller의 루트 검사에 immutable 번들의 오프라인 회귀를 연결합니다."""
from pathlib import Path
import subprocess
import sys
import unittest


class BundledRegressionTests(unittest.TestCase):
    def test_archived_033_offline_regressions(self):
        root = Path(__file__).resolve().parents[1]
        bundle = root / 'distribution/releases/0.3.3/universal-ai-starter'
        # A separate interpreter keeps the bundle's same-named imports isolated.
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(bundle / 'tests'),
             '-p', 'test_*.py', '-v'], cwd=root, capture_output=True, timeout=300)
        self.assertEqual(result.returncode, 0,
                         result.stdout.decode('utf-8', errors='replace') +
                         result.stderr.decode('utf-8', errors='replace'))
        self.assertIn(b'Ran ', result.stderr)
