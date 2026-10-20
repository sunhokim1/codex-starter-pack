"""Offline Windows installer checks; never authenticate, install software or call models."""
import hashlib
import json
import os
import re
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
        release = {'version': '0.3.3', 'sha256': {name: hashlib.sha256(data).hexdigest()
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

    def test_staged_bootstrap_precedes_personal_skill_promotion(self):
        text = (ROOT/'scripts/install_from_github.ps1').read_text(encoding='utf-8')
        bootstrap = text.index('& ([scriptblock]::Create($bootstrapText))')
        self.assertLess(bootstrap, text.index('Move-Item -LiteralPath $installed -Destination $backup'))
        self.assertLess(bootstrap, text.index("Move-Item -LiteralPath (Join-Path $stage"))
        self.assertIn("$bootstrapDirectory = Join-Path $stage 'universal-ai-starter/scripts'", text)

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
        self.assert_bad_zip(lambda files, release: release.update(version='0.3.2'))
        self.assert_bad_zip(lambda files, release: release.update(version='0.4.0'))
        self.assert_bad_zip(lambda files, release: files.update({'universal-ai-starter/extra': b'bad'}))

    def test_case_alias_and_nested_skill_rejected(self):
        self.assert_bad_zip(lambda files, release: files.update({'universal-ai-starter/skill.md': b'bad'}))

        def nested(files, release):
            name = 'universal-ai-starter/assets/runner/SKILL.md'
            files[name] = b'duplicate discovery'
            release['sha256'][name] = hashlib.sha256(files[name]).hexdigest()
        self.assert_bad_zip(nested)

    def test_download_url_allowlist(self):
        self.run_ps("""
$pin='1f1a8e97e097e457cc1369c26cc652dfb57e15c0'
$null=Assert-StarterUrl "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$pin/universal-ai-starter.zip"
foreach ($url in @('http://raw.githubusercontent.com/a',
    'https://raw.githubusercontent.com.evil.test/a',
    "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/main/universal-ai-starter.zip",
    "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$pin/universal-ai-starter.zip?x=1",
    "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$pin/other.ps1",
    "https://user@raw.githubusercontent.com/sunhokim1/codex-starter-pack/$pin/universal-ai-starter.zip")) {
    $rejected=$false
    try { $null=Assert-StarterUrl $url } catch { $rejected=$true }
    if (-not $rejected) { throw 'unsafe URL accepted' }
}
""")

    def test_snapshot_manifest_must_match_independent_zip_pin(self):
        self.write_zip()
        self.run_ps("""
$snapshot=[pscustomobject]@{version='0.3.3';sha256=[pscustomobject]@{wrong=('a'*64)}}
$rejected=$false
try { Expand-VerifiedStarter ([IO.File]::ReadAllBytes((Join-Path $env:STARTER_WORK 'bundle.zip'))) (Join-Path $env:STARTER_WORK 'stage') $snapshot }
catch { $rejected=$true }
if (-not $rejected -or (Test-Path (Join-Path $env:STARTER_WORK 'stage'))) { throw 'snapshot mismatch wrote files' }
foreach ($commit in @('main','abcd',('A'*40))) {
    $rejected=$false
    try { Get-StarterSnapshot $commit '0.3.3' } catch { $rejected=$true }
    if (-not $rejected) { throw 'mutable/invalid snapshot accepted' }
}
function Get-StarterBytes { throw 'offline network failure' }
$rejected=$false
try { Get-StarterSnapshot ('a'*40) '0.3.3' } catch { $rejected=$true }
if (-not $rejected) { throw 'network error ignored' }
""")

    def test_snapshot_config_and_metadata_validation(self):
        self.run_ps("""
$global:ConfigText="starter:`n  version: `"0.3.3`"`n"
$validRelease='{"version":"0.3.3","sha256":{"asset":"' + ('a'*64) + '"}}'
$global:ReleaseText=$validRelease
function Get-StarterBytes {
    param($Url, $Limit)
    if ($Url -notlike ('https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/' + ('a'*40) + '/*')) { throw 'not pinned' }
    if ($Url.EndsWith('config.yaml')) { return ,([Text.Encoding]::UTF8.GetBytes($global:ConfigText)) }
    return ,([Text.Encoding]::UTF8.GetBytes($global:ReleaseText))
}
$snapshot=Get-StarterSnapshot ('a'*40) '0.3.3'
if ($snapshot.version -ne '0.3.3') { throw 'valid metadata rejected' }
foreach ($value in @('{', '{"version":"0.3.2","sha256":{}}', '{"version":"0.3.3"}',
    '{"version":"0.3.3","sha256":{}}', '{"version":"0.3.3","sha256":{"asset":"hash"}}')) {
    $global:ReleaseText=$value
    $rejected=$false
    try { Get-StarterSnapshot ('a'*40) '0.3.3' } catch { $rejected=$true }
    if (-not $rejected) { throw 'invalid release accepted' }
}
$global:ReleaseText=$validRelease
foreach ($value in @("starter:`n  version: `"0.3.2`"`n",
    "starter:`n  version: 0.3.2`nother:`n  version: 0.3.3`n",
    "starter:`n  version: 0.3.3`n  version: 0.3.2`n",
    "starter:`n  version: 0.3.3`nstarter:`n  version: 0.3.2`n",
    "starter:`n  version: '0.3.3`"`n")) {
    $global:ConfigText=$value
    $rejected=$false
    try { Get-StarterSnapshot ('a'*40) '0.3.3' } catch { $rejected=$true }
    if (-not $rejected) { throw 'wrong/ambiguous config accepted' }
}
""")

    def test_managed_bundle_preserves_argument_boundaries_and_failure(self):
        self.run_ps("""
function Get-Command { return [pscustomobject]@{Source='MockPython'} }
function MockPython {
    $global:LASTEXITCODE=0
    if ($args[0] -ne '-c') { $global:Captured=@($args); $global:LASTEXITCODE=$global:InstallExit }
}
$global:InstallExit=0
$target=Join-Path $env:STARTER_WORK "한글 공백 & ' [특수] `$경로"
Invoke-StarterManagedBundle $env:STARTER_WORK $target
if ($global:Captured[2] -cne $target -or $global:Captured.Count -ne 5 -or
    $global:Captured[3] -ne '--adopt' -or $global:Captured[4] -ne '--no-autostart') { throw 'argument corruption' }
$global:InstallExit=9
$rejected=$false
try { Invoke-StarterManagedBundle $env:STARTER_WORK $target } catch { $rejected=$true }
if (-not $rejected) { throw 'preflight/install failure ignored' }
function Get-Command { return $null }
$rejected=$false
try { Invoke-StarterManagedBundle $env:STARTER_WORK $target } catch { $rejected=$true }
if (-not $rejected) { throw 'missing Python accepted' }
if (Test-Path -LiteralPath $target) { throw 'mock wrote project' }
""")

    def test_post_install_requires_connection_and_paths(self):
        self.run_ps("""
$rejected=$false
try { Assert-StarterInstalled $env:STARTER_WORK '0.3.3' } catch { $rejected=$true }
if (-not $rejected) { throw 'missing connection accepted' }
$null=New-Item -ItemType Directory -Path (Join-Path $env:STARTER_WORK '.ai')
'{"version":"0.3.3","python":"missing"}' | Set-Content (Join-Path $env:STARTER_WORK '.ai/sev.json')
$rejected=$false
try { Assert-StarterInstalled $env:STARTER_WORK '0.3.3' } catch { $rejected=$true }
if (-not $rejected) { throw 'incomplete install accepted' }
""")

    def test_post_install_valid_fixture_and_each_required_path(self):
        self.run_ps("""
$null=New-Item -ItemType Directory -Path (Join-Path $env:STARTER_WORK '.ai')
$config=@{version='0.3.3'}
foreach ($key in @('python', 'service', 'state', 'runner', 'project_runner')) {
    $path=Join-Path $env:STARTER_WORK ($key + '.fixture')
    [IO.File]::WriteAllText($path, 'fixture only; never executed')
    $config[$key]=$path
}
$connection=Join-Path $env:STARTER_WORK '.ai/sev.json'
$config | ConvertTo-Json | Set-Content -LiteralPath $connection
Assert-StarterInstalled $env:STARTER_WORK '0.3.3'
foreach ($key in @('python', 'service', 'state', 'runner', 'project_runner', 'version')) {
    $saved=$config[$key]
    $config[$key]='missing'
    $config | ConvertTo-Json | Set-Content -LiteralPath $connection
    $rejected=$false
    try { Assert-StarterInstalled $env:STARTER_WORK '0.3.3' } catch { $rejected=$true }
    if (-not $rejected) { throw ('invalid installed field accepted: ' + $key) }
    $config[$key]=$saved
}
""")

    def test_saved_file_cancel_and_error_exit_codes(self):
        installer = str(ROOT/'scripts/install_from_github.ps1')
        for args, code, status in [(['-Manager'], 2, 'cancelled'),
                                   (['-Manager', '-Target', str(self.work/'한글 & project'),
                                     '-SnapshotCommit', 'main', '-ExpectedVersion', '0.3.3'], 1, 'error')]:
            result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', installer, *args],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            records = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            self.assertEqual(records[-1]['status'], status)
            self.assertEqual(records[-1]['exitCode'], code)

    def test_oneclick_iex_cancellation_keeps_calling_session_alive(self):
        wrapper = self.work/'oneclick.ps1'
        wrapper.write_text("""function Read-Host { return '' }
Invoke-Expression ([IO.File]::ReadAllText($env:STARTER_INSTALLER))
Write-Output 'CALLER_STILL_RUNNING'
""", encoding='utf-8-sig')
        env = dict(os.environ, STARTER_INSTALLER=str(ROOT/'scripts/install_from_github.ps1'))
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-Mta', '-File', str(wrapper)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('CALLER_STILL_RUNNING', result.stdout)

    def test_saved_file_managed_success_and_preflight_failure_with_offline_boundary(self):
        # Execute the real parameter/exit/cleanup shell with only network and
        # installation boundaries replaced. No installed runtime is touched.
        source = (ROOT/'scripts/install_from_github.ps1').read_text(encoding='utf-8-sig')
        target = str(self.work/"한글 공백 & ' [project] $value")
        env = dict(os.environ, EXPECTED_TARGET=target)
        for fail in (False, True):
            replacements = {
                'Get-StarterSnapshot': "return [pscustomobject]@{version='0.3.3'}",
                'Get-StarterPublicZip': 'return ,([byte[]]@(1))',
                'Expand-VerifiedStarter': "param([byte[]]$Bytes, [string]$Stage, $Snapshot)\nif ($Snapshot.version -ne '0.3.3') { throw 'missing snapshot' }",
                'Invoke-StarterManagedBundle': "param([string]$Directory, [string]$Target)\nif ($Target -cne $env:EXPECTED_TARGET) { throw 'target changed' }\n" +
                    ("throw 'mock native preflight failed'" if fail else ''),
                'Assert-StarterInstalled': "param([string]$Target, [string]$Version)\nif ($Target -cne $env:EXPECTED_TARGET -or $Version -ne '0.3.3') { throw 'postcheck arguments' }",
            }
            script = source
            for name, body in replacements.items():
                script, count = re.subn(r'^    function ' + name + r'[^\n]*\{.*?^    }\n',
                                        lambda _: f'    function {name} {{\n{body}\n    }}\n',
                                        script, count=1, flags=re.M | re.S)
                self.assertEqual(count, 1, name)
            fixture = self.work/'offline-installer.ps1'
            fixture.write_text(script, encoding='utf-8-sig')
            result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(fixture),
                                     '-Manager', '-Target', target, '-SnapshotCommit', 'a'*40,
                                     '-ExpectedVersion', '0.3.3'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1 if fail else 0, result.stdout + result.stderr)
            records = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            self.assertEqual(records[-1]['status'], 'error' if fail else 'installed')
            if not fail:
                self.assertFalse(records[-1]['personalSkillReplaced'])
                self.assertFalse(records[-1]['autostart'])
            self.assertFalse(Path(target).exists())

    def test_manager_branch_does_not_promote_personal_skill_or_bootstrap(self):
        text = (ROOT/'scripts/install_from_github.ps1').read_text(encoding='utf-8-sig')
        branch = text[text.index('        if ($Manager) {'):text.index('        $null = Assert-StarterPath $installed')]
        self.assertIn('Invoke-StarterManagedBundle', branch)
        self.assertIn('Assert-StarterInstalled', branch)
        self.assertIn('return', branch)
        self.assertNotIn('Move-Item', branch)
        self.assertNotIn('bootstrapText', branch)
        self.assertIn('$request.AllowAutoRedirect = $false', text)
        self.assertIn('$request.Timeout = 30000', text)
        self.assertNotIn('ServerCertificateValidationCallback', text)

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
