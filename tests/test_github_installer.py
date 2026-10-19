"""Offline Windows installer checks; never authenticate, install software or call models."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which('pwsh') or shutil.which('powershell')


@unittest.skipUnless(os.name == 'nt' and POWERSHELL, 'Windows PowerShell required')
class GithubInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix='installer-test-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def run_ps(self, body):
        # Parse and load only function definitions; the installer entry point never executes.
        script = self.work/'check.ps1'
        script.write_text("""$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($env:STARTER_INSTALLER,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true) |
    ForEach-Object { Invoke-Expression $_.Extent.Text }
""" + body, encoding='utf-8-sig')
        env = dict(os.environ, STARTER_INSTALLER=str(ROOT/'scripts/install_from_github.ps1'),
                   STARTER_WORK=str(self.work), STARTER_BOOTSTRAP=str(ROOT/'distribution/skill/scripts/bootstrap.ps1'))
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-Mta', '-File', str(script)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_zip(self, change=None):
        manifest = json.loads((ROOT/'distribution/manifest.json').read_text())
        files = {f'universal-ai-starter/{dest}': (ROOT/src).read_bytes()
                 for dest, src in manifest['skill_files'].items()}
        files.update({f'universal-ai-starter/assets/starter/{name}': (ROOT/name).read_bytes()
                      for name in manifest['template_files']})
        release = {'version': '0.3.1', 'sha256': {name: hashlib.sha256(data).hexdigest()
                                                for name, data in files.items()}}
        if change:
            change(files, release)
        files['universal-ai-starter/release.json'] = json.dumps(release).encode()
        with zipfile.ZipFile(self.work/'bundle.zip', 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)

    def test_parser_and_valid_bundle(self):
        self.write_zip()
        self.run_ps("""
$stage=Join-Path $env:STARTER_WORK 'stage'
Expand-VerifiedStarter ([IO.File]::ReadAllBytes((Join-Path $env:STARTER_WORK 'bundle.zip'))) $stage
if (-not (Test-Path -LiteralPath (Join-Path $stage 'universal-ai-starter/assets/runner/SKILL.template.md'))) { throw 'missing runner template' }
if (Test-Path -LiteralPath (Join-Path $stage 'universal-ai-starter/assets/runner/SKILL.md')) { throw 'duplicate skill discovery' }
""")

    def assert_bad_zip(self, change):
        self.write_zip(change)
        self.run_ps("""
$stage=Join-Path $env:STARTER_WORK 'stage'
$rejected=$false
try { Expand-VerifiedStarter ([IO.File]::ReadAllBytes((Join-Path $env:STARTER_WORK 'bundle.zip'))) $stage }
catch { $rejected=$true }
if (-not $rejected) { throw 'unsafe ZIP accepted' }
if (Test-Path -LiteralPath $stage) { throw 'invalid ZIP wrote staging files' }
""")

    def test_tampered_download_rejected_before_writes(self):
        self.assert_bad_zip(lambda files, release: files.update({'universal-ai-starter/SKILL.md': b'tampered'}))

    def test_traversal_and_windows_aliases_rejected(self):
        for name in ('../escape', 'universal-ai-starter/../escape',
                     'universal-ai-starter/a:stream', 'universal-ai-starter/CON.txt',
                     'universal-ai-starter/a.', 'universal-ai-starter/a\\b'):
            with self.subTest(name=name):
                self.assert_bad_zip(lambda files, release: files.update({name: b'bad'}))

    def test_wrong_release_and_unhashed_extra_rejected(self):
        self.assert_bad_zip(lambda files, release: release.update(version='0.4.0'))
        self.assert_bad_zip(lambda files, release: files.update({'universal-ai-starter/extra': b'bad'}))

    def test_case_alias_and_nested_skill_rejected(self):
        self.assert_bad_zip(lambda files, release: files.update({'universal-ai-starter/skill.md': b'bad'}))

        def nested(files, release):
            name = 'universal-ai-starter/assets/runner/SKILL.md'
            files[name] = b'duplicate discovery'
            release['sha256'][name] = hashlib.sha256(files[name]).hexdigest()
        self.assert_bad_zip(nested)

    def test_target_and_bootstrap_adopted_project_preserves_facts(self):
        project = self.work/'project'
        (project/'.ai').mkdir(parents=True)
        for name in ('AGENTS.md', 'PROJECT.md', 'README.md', '.ai/models.yaml', '.ai/verification.yaml'):
            (project/name).write_text('existing project facts ' + name)
        before = {p: p.read_bytes() for p in project.rglob('*') if p.is_file()}
        self.run_ps("""
function Read-Host { return '' }
# Force the simple user-selected path alternative without opening a real dialog.
if ([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') {
    if ($null -ne (Select-StarterTarget '')) { throw 'cancel did not stop' }
}
$rejected=$false
try { Select-StarterTarget ([IO.Path]::GetPathRoot($env:STARTER_WORK)) } catch { $rejected=$true }
if (-not $rejected) { throw 'drive root accepted' }
$target=Select-StarterTarget (Join-Path $env:STARTER_WORK 'project')
function Get-Command { param($Name) if ($Name -eq 'python.exe') { return [pscustomobject]@{Source='python.exe'} } }
function python.exe { $global:LASTEXITCODE=0; if ($args[0] -ne '-c') { $global:StarterCalled=$args[0] } }
& $env:STARTER_BOOTSTRAP -Target $target
if ([IO.Path]::GetFileName($global:StarterCalled) -ne 'install_sev.py') { throw 'adopted project used scaffold' }
""")
        self.assertEqual(before, {p: p.read_bytes() for p in project.rglob('*') if p.is_file()})

    def test_bootstrap_new_project_and_failure(self):
        self.run_ps("""
function Get-Command { param($Name) if ($Name -eq 'python.exe') { return [pscustomobject]@{Source='python.exe'} } }
function python.exe { $global:LASTEXITCODE=0; if ($args[0] -ne '-c') { $global:StarterCalled=$args[0]; $global:LASTEXITCODE=2 } }
$rejected=$false
try { & $env:STARTER_BOOTSTRAP -Target (Join-Path $env:STARTER_WORK 'new-project') } catch { $rejected=$true }
if (-not $rejected) { throw 'failed bootstrap reported success' }
if ([IO.Path]::GetFileName($global:StarterCalled) -ne 'scaffold.py') { throw 'new project did not use scaffold' }
if (Test-Path -LiteralPath (Join-Path $env:STARTER_WORK 'new-project')) { throw 'mock bootstrap wrote project files' }
""")


if __name__ == '__main__':
    unittest.main()
