"""Native sandbox contract tests; no real installation or permission changes."""
import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import install_sev as installer


class SandboxPreflightTests(unittest.TestCase):
    def run_probe(self, side_effect=None, code=0, marker=True):
        def execute(command, **kwargs):
            self.assertEqual(command[:7], ['native-codex', 'sandbox', '--include-managed-config',
                '--permission-profile', ':workspace', '--', 'selected-python'])
            self.assertEqual(kwargs['cwd'], Path.cwd())
            self.assertEqual(kwargs['timeout'], 45)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', command)
            self.assertEqual(command[7:9], ['-I', '-c'])
            if side_effect:
                raise side_effect
            return SimpleNamespace(returncode=code,
                stdout=command[-1]+'\n' if marker else '', stderr='password="fixture-secret"')
        with patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.shutil, 'which', return_value='native-codex'), \
             patch.object(installer.subprocess, 'run', side_effect=execute) as call:
            result = installer.sandbox_preflight('selected-python', Path.cwd())
        self.assertEqual(call.call_count, 1)
        return result

    def test_pass_requires_native_managed_profile_and_probe_marker(self):
        self.assertEqual(self.run_probe()['status'], 'passed')

    def test_non_windows_is_not_a_pass_and_does_not_launch(self):
        with patch.object(installer.sys, 'platform', 'linux'), patch.object(installer.subprocess, 'run') as call:
            self.assertEqual(installer.sandbox_preflight('python', Path.cwd())['status'], 'not_applicable')
        call.assert_not_called()

    def test_missing_cli_fails_without_execution(self):
        with patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.shutil, 'which', return_value=None), \
             patch.object(installer.subprocess, 'run') as call:
            with self.assertRaisesRegex(RuntimeError, 'CLI missing from PATH'):
                installer.sandbox_preflight('python', Path.cwd())
        call.assert_not_called()

    def test_timeout_fails_without_retry_or_unrestricted_fallback(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.run_probe(subprocess.TimeoutExpired('native-codex', 45))

    def test_failed_startup_is_actionable(self):
        with self.assertRaisesRegex(RuntimeError, 'could not launch native sandbox'):
            self.run_probe(PermissionError('fixture access denied'))

    def test_denied_interpreter_or_unsupported_option_fails_and_redacts(self):
        for code in (1, 2):
            with self.subTest(code=code), self.assertRaises(RuntimeError) as error:
                self.run_probe(code=code)
            text = str(error.exception)
            self.assertIn('Runtime paths:', text)
            self.assertIn('No permissions were granted', text)
            self.assertNotIn('fixture-secret', text)
            self.assertLess(len(text), 4000)

    def test_exit_zero_without_probe_completion_is_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'access failed'):
            self.run_probe(marker=False)

    def test_smoke_program_really_checks_stdlib_child_and_workspace(self):
        # Execute only the bounded, non-secret Python body, never a real sandbox/install.
        def execute(command, **kwargs):
            result = REAL_RUN([sys.executable, *command[7:]], cwd=kwargs['cwd'],
                              capture_output=True, text=True, timeout=20)
            return result
        with patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.shutil, 'which', return_value='native-codex'), \
             patch.object(installer.subprocess, 'run', side_effect=execute):
            self.assertEqual(installer.sandbox_preflight('selected-python', Path.cwd())['status'], 'passed')
        self.assertEqual(list(Path.cwd().glob('.starter-probe-*')), [])


REAL_RUN = subprocess.run
