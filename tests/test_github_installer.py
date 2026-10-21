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
PS7 = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PowerShell/7/pwsh.exe'
POWERSHELL = shutil.which('pwsh') or (str(PS7) if PS7.is_file() else shutil.which('powershell.exe'))


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
        release = {'version': '0.4.0', 'sha256': {name: hashlib.sha256(data).hexdigest()
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
        self.assert_bad_zip(lambda files, release: release.update(version='0.3.2'))
        self.assert_bad_zip(lambda files, release: release.update(version='0.3.3'))
        self.assert_bad_zip(lambda files, release: files.update({'universal-ai-starter/extra': b'bad'}))

    def test_case_alias_and_nested_skill_rejected(self):
        self.assert_bad_zip(lambda files, release: files.update({'universal-ai-starter/skill.md': b'bad'}))

        def nested(files, release):
            name = 'universal-ai-starter/assets/runner/SKILL.md'
            files[name] = b'duplicate discovery'
            release['sha256'][name] = hashlib.sha256(files[name]).hexdigest()
        self.assert_bad_zip(nested)

    def test_explicit_inputs_and_no_global_promotion(self):
        text=(ROOT/'scripts/install_from_github.ps1').read_text(encoding='utf-8-sig')
        self.assertNotIn('Move-Item',text)
        self.assertIn('RuntimeRoot',text);self.assertIn('ConnectionFile',text)
        self.assertNotIn(".codex/sev",text)
        self.run_ps("""
$pin='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
$null=Assert-StarterUrl "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$pin/distribution/releases/0.4.0/universal-ai-starter.zip"
foreach ($url in @("https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$pin/universal-ai-starter.zip",'https://evil.example/a','http://raw.githubusercontent.com/a')) {
    $bad=$false;try { $null=Assert-StarterUrl $url } catch { $bad=$true };if(-not $bad){throw 'unsafe URL accepted'}
}
""")

    def test_snapshot_uses_new_release_without_private_bootstrap(self):
        self.assertEqual((ROOT/'scripts/install_from_github.ps1').read_bytes(),
                         (ROOT/'distribution/releases/0.4.0/universal-ai-starter/scripts/install_from_github.ps1').read_bytes())
        self.run_ps("""
function Get-StarterBytes([string]$Url,[int]$Limit) {
    if ($Url -notmatch '/distribution/releases/0.4.0/universal-ai-starter/release.json$') {throw 'wrong metadata'}
    return ,[Text.Encoding]::UTF8.GetBytes('{"version":"0.4.0","sha256":{"universal-ai-starter/asset":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}')
}
$snapshot=Get-StarterSnapshot ('a'*40) '0.4.0'
if ($snapshot.version -ne '0.4.0') {throw 'new version rejected'}
$bad=$false;try{Get-StarterSnapshot ('a'*40) '0.3.3'}catch{$bad=$true};if(-not $bad){throw 'legacy accepted'}
""")

    def test_default_main_lookup_pins_one_commit(self):
        self.run_ps("""
$script:calls=0
function Get-StarterBytes([string]$Url,[int]$Limit) {
    $script:calls++
    if ($Url -cne 'https://api.github.com/repos/sunhokim1/codex-starter-pack/commits/main') {throw 'wrong lookup'}
    return ,[Text.Encoding]::UTF8.GetBytes('{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
}
$pin=Resolve-StarterCommit
if ($pin -cne ('a'*40) -or $script:calls -ne 1) {throw 'main not pinned once'}
""")

    def test_reviewed_bundle_entry_point_completes_real_source_install(self):
        target=Path(self.temp.name)/'project';target.mkdir()
        bundle=ROOT/'distribution/releases/0.4.0/universal-ai-starter'
        command=[POWERSHELL,'-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/install_from_github.ps1'),
                 '-Target',str(target),'-BundlePath',str(bundle),'-Manager','-SnapshotCommit','a'*40]
        # A local reviewed bundle and snapshot are exclusive; manager result pin is optional for this local fixture.
        command=command[:-2]
        result=subprocess.run(command,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,repr(result.stdout)+repr(result.stderr))
        data=json.loads(result.stdout.decode('utf-8-sig').strip().splitlines()[-1])
        self.assertEqual(data['status'],'installed');self.assertEqual(data['sourceStatus'],'installed')
        self.assertEqual(data['revStatus'],'preparation_needed');self.assertFalse(data['autostart'])
        self.assertTrue((target/'.ai/starter-source/assets/runner/run.py').is_file())
        self.assertFalse((target/'.ai/rev.json').exists());self.assertFalse((target/'.ai/sev.json').exists())
        receipt=target/'.ai/source-install.json';newer=json.loads(receipt.read_text());newer['version']='9.0.0'
        receipt.write_text(json.dumps(newer))
        result=subprocess.run(command[:-1],capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,repr(result.stdout)+repr(result.stderr))
        data=json.loads(result.stdout.decode('utf-8-sig').strip().splitlines()[-1])
        self.assertEqual(data['source_status'],'newer');self.assertFalse(data['changed'])

if __name__=='__main__':unittest.main()
