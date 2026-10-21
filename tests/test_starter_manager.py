"""관리기 코어의 오프라인 fixture 및 Windows byte-range 잠금 회귀 검사."""
import os
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PS7 = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PowerShell/7/pwsh.exe'
POWERSHELL = shutil.which('pwsh') or (str(PS7) if PS7.is_file() else shutil.which('powershell.exe'))
CSC = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'


@unittest.skipUnless(os.name == 'nt' and POWERSHELL and CSC.is_file(), 'Windows 및 로컬 .NET Framework csc 필요')
class StarterManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sm-', dir=ROOT)
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        cls.output = cls.work / 'bin'
        result = subprocess.run(
            [POWERSHELL, '-NoProfile', '-NonInteractive', '-File',
             str(ROOT / 'apps/starter-manager/build-core.ps1'), '-OutputDirectory', str(cls.output)],
            capture_output=True, timeout=60)
        if result.returncode:
            raise AssertionError(f'관리기 코어 빌드 실패: {result.stdout!r} {result.stderr!r}')
        cls.exe = cls.output / 'StarterManager.CoreTests.exe'
        gui_build = subprocess.run(
            [POWERSHELL, '-NoProfile', '-NonInteractive', '-File',
             str(ROOT / 'apps/starter-manager/build.ps1'), '-OutputDirectory', str(cls.output)],
            capture_output=True, timeout=60)
        if gui_build.returncode:
            raise AssertionError(f'관리기 GUI 빌드 실패: {gui_build.stdout!r} {gui_build.stderr!r}')
        cls.gui = cls.output / 'CodexStarterManager.exe'

    def test_gui_diagnostics_are_fixture_only_and_create_real_forms(self):
        fixture_root = self.work / 'g'
        fixture_root.mkdir()
        for mode in ('--self-test', '--smoke-test'):
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.gui), mode, str(fixture_root)],
                                        capture_output=True, timeout=45)
                report = fixture_root / (mode[2:] + '-result.json')
                evidence = report.read_text(encoding='utf-8') if report.exists() else '결과 파일 없음'
                self.assertEqual(result.returncode, 0, evidence)
                data = json.loads(evidence)
                self.assertEqual(data['status'], 'passed')
                self.assertFalse(data['network'])
                self.assertFalse(data['realInstallation'])
                self.assertFalse(data['userSettings'])
                self.assertTrue(data['actualForm'])
                self.assertGreaterEqual(data['assertions'], 17)
        self.assertFalse(list(fixture_root.glob('g-*')), '진단 임시 폴더 정리 필요')

    def test_gui_rejects_incomplete_diagnostic_arguments_without_startup(self):
        for args in (['--self-test'], ['--smoke-test'], ['--unknown'],
                     ['--smoke-test', str(self.work / 'missing')]):
            with self.subTest(args=args):
                result = subprocess.run([str(self.gui)] + args, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2)

    def test_app_package_contains_only_reviewed_payload_and_matching_hashes(self):
        output = self.work / 'package'
        result = subprocess.run(
            [POWERSHELL, '-NoProfile', '-NonInteractive', '-File',
             str(ROOT / 'apps/starter-manager/package.ps1'),
             '-BinaryPath', str(self.gui), '-OutputDirectory', str(output)],
            capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, repr(result.stdout) + repr(result.stderr))
        manifest = json.loads((output / 'artifacts.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['appVersion'], '0.2.0')
        archive_path = output / 'CodexStarterManager-0.2.0-win.zip'
        self.assertEqual(manifest['archive'], archive_path.name)
        self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(), manifest['archiveSha256'])
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(archive.namelist(), ['CodexStarterManager.exe', 'README.md'])
            self.assertEqual(archive.read('CodexStarterManager.exe'), self.gui.read_bytes())
            self.assertEqual(archive.read('README.md'), (ROOT / 'apps/starter-manager/README.md').read_bytes())
            self.assertEqual({entry['path'] for entry in manifest['files']}, set(archive.namelist()))
            for entry in manifest['files']:
                content = archive.read(entry['path'])
                self.assertEqual(entry['bytes'], len(content))
                self.assertEqual(entry['sha256'], hashlib.sha256(content).hexdigest())

    def test_deterministic_core_fixtures_and_native_process_smoke(self):
        result = subprocess.run([str(self.exe), '--self-test', str(self.work)],
                                capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, repr(result.stdout) + repr(result.stderr))
        self.assertIn(b'deterministic fixture assertions', result.stdout)
        self.assertIn(b'No network or real installation', result.stdout)

    def test_csharp_lock_conflicts_with_installer_msvcrt_byte_lock(self):
        import msvcrt
        lock = self.work / 'msvcrt.lock'
        lock.write_bytes(b'0')
        # Readiness line is flushed by Console.WriteLine; teardown releases on stdin EOF.
        with subprocess.Popen([str(self.exe), '--hold-lock', str(lock)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                self.assertEqual(process.stdout.readline().strip(), b'locked')
                with lock.open('r+b') as stream:
                    with self.assertRaises(OSError):
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            finally:
                process.communicate(b'\n', timeout=10)
            self.assertEqual(process.returncode, 0)
        with lock.open('r+b') as stream:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
