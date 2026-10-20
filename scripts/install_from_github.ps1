# Public installer: irm https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/main/scripts/install_from_github.ps1 | iex
# Saved-file usage: .\install_from_github.ps1 [-Target 'C:\your\project']
[CmdletBinding()]
param(
    [Parameter(Position=0)][string]$Target,
    [switch]$Manager,
    [string]$SnapshotCommit,
    [string]$ExpectedVersion
)
$starterExitCode = 0
try {
& {
    param([string]$Target, [bool]$Manager, [string]$SnapshotCommit, [string]$ExpectedVersion)
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    $PSNativeCommandUseErrorActionPreference = $false

    function Assert-StarterPath([string]$Path) {
        $full = [IO.Path]::GetFullPath($Path)
        $current = $full
        while ($current) {
            if (Test-Path -LiteralPath $current) {
                $item = Get-Item -LiteralPath $current -Force
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    throw "Links/reparse points are not allowed: $current"
                }
            }
            $parent = [IO.Directory]::GetParent($current)
            if (-not $parent) { break }
            $current = $parent.FullName
        }
        return $full
    }

    function Select-StarterTarget([string]$Value) {
        if (-not $Value) {
            if ([Threading.Thread]::CurrentThread.GetApartmentState() -eq 'STA') {
                Add-Type -AssemblyName System.Windows.Forms
                $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
                $dialog.Description = 'Select the project folder for Universal AI Starter'
                try {
                    if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { return $null }
                    $Value = $dialog.SelectedPath
                } finally { $dialog.Dispose() }
            } else {
                # PowerShell 7 can run in MTA; avoid spawning a second installer.
                $Value = Read-Host 'Project folder path (blank cancels; paste a path or drag a folder here)'
                $Value = $Value.Trim().Trim('"')
            }
        }
        if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
        if (-not [IO.Path]::IsPathRooted($Value)) { $Value = Join-Path (Get-Location).Path $Value }
        $full = Assert-StarterPath $Value
        if ($full.TrimEnd('\', '/') -eq [IO.Path]::GetPathRoot($full).TrimEnd('\', '/')) {
            throw 'Select a project folder, not a drive root.'
        }
        if ((Test-Path -LiteralPath $full) -and -not (Test-Path -LiteralPath $full -PathType Container)) {
            throw 'Target must be a directory.'
        }
        foreach ($relative in @('AGENTS.md', 'PROJECT.md', 'README.md', '.ai', '.ai/config.yaml',
                '.ai/models.yaml', '.ai/routing.yaml', '.ai/verification.yaml', '.ai/sev.json')) {
            $null = Assert-StarterPath (Join-Path $full $relative)
        }
        return $full
    }

    function Assert-StarterUrl([string]$Value) {
        $uri = $null
        if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri) -or
            $uri.Scheme -cne 'https' -or $uri.Host -cne 'raw.githubusercontent.com' -or
            $uri.Port -ne 443 -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or
            $uri.AbsolutePath -cnotmatch '^/sunhokim1/codex-starter-pack/[0-9a-f]{40}/(universal-ai-starter\.zip|scripts/install_from_github\.ps1|\.ai/config\.yaml|distribution/releases/0\.3\.3/universal-ai-starter/release\.json)$') {
            throw '허용되지 않은 다운로드 URL입니다.'
        }
        return $uri
    }

    function Get-StarterBytes([string]$Url, [int]$Limit) {
        $uri = Assert-StarterUrl $Url
        if ($Limit -le 0 -or $Limit -gt 32MB) { throw 'Invalid download limit.' }
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $request = [Net.HttpWebRequest]::Create($uri)
        $request.AllowAutoRedirect = $false
        $request.Timeout = 30000
        $request.ReadWriteTimeout = 30000
        $response = $null
        $inputStream = $null
        $output = New-Object IO.MemoryStream
        $clock = [Diagnostics.Stopwatch]::StartNew()
        try {
            $response = $request.GetResponse()
            if ([int]$response.StatusCode -ne 200 -or $response.ContentLength -gt $Limit) {
                throw 'Unexpected HTTP status, redirect or download size.'
            }
            $inputStream = $response.GetResponseStream()
            $buffer = New-Object byte[] 8192
            while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                if ($clock.Elapsed.TotalSeconds -gt 60 -or $output.Length + $count -gt $Limit) {
                    throw 'Download exceeded time or size limit.'
                }
                $output.Write($buffer, 0, $count)
            }
            if ($output.Length -eq 0) { throw 'Empty download.' }
            return ,$output.ToArray()
        } finally {
            if ($inputStream) { $inputStream.Dispose() }
            if ($response) { $response.Dispose() }
            $output.Dispose()
            $request.Abort()
        }
    }

    function Get-StarterPublicZip {
        # The ZIP pin is independent of the main snapshot selected by the manager.
        return ,(Get-StarterBytes 'https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/1f1a8e97e097e457cc1369c26cc652dfb57e15c0/universal-ai-starter.zip' 32MB)
    }

    function Get-StarterSnapshot([string]$Commit, [string]$Version) {
        if ($Commit -cnotmatch '^[0-9a-f]{40}$' -or $Version -cne '0.3.3') {
            throw '지원하지 않는 snapshot 또는 배포 버전입니다.'
        }
        $base = "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$Commit"
        $config = [Text.Encoding]::UTF8.GetString((Get-StarterBytes "$base/.ai/config.yaml" 1MB))
        # Read only the expected starter block; another section's version must
        # not satisfy this check. Reject duplicate keys and mismatched quotes.
        $blocks = [regex]::Matches($config, '(?m)^starter:[ \t]*\r?\n((?:[ \t]+[^\r\n]*(?:\r?\n|$)|\r?\n)*)')
        if ($blocks.Count -ne 1 -or
            [regex]::Matches($config, '(?m)^starter:').Count -ne 1 -or
            [regex]::Matches($blocks[0].Groups[1].Value, '(?m)^  version:').Count -ne 1 -or
            $blocks[0].Groups[1].Value -cnotmatch '(?m)^  version: *(?<quote>[\x22\x27]?)0\.3\.3\k<quote> *\r?$') {
            throw 'Snapshot 설정 버전이 일치하지 않습니다.'
        }
        $release = [Text.Encoding]::UTF8.GetString((Get-StarterBytes "$base/distribution/releases/0.3.3/universal-ai-starter/release.json" 1MB)) | ConvertFrom-Json
        if ($release.version -cne $Version -or -not $release.sha256) { throw 'Snapshot release metadata가 올바르지 않습니다.' }
        # Reject malformed manifests before downloading the ZIP as well as
        # comparing them with the independent ZIP manifest during extraction.
        Assert-StarterReleaseMatch $release $release
        return $release
    }

    function Assert-StarterReleaseMatch($Snapshot, $Release) {
        if ($Snapshot.version -cne $Release.version) { throw 'Snapshot/ZIP version mismatch.' }
        $expected = @($Snapshot.sha256.PSObject.Properties)
        $actual = @($Release.sha256.PSObject.Properties)
        if ($expected.Count -ne $actual.Count -or $expected.Count -eq 0) { throw 'Snapshot/ZIP manifest mismatch.' }
        foreach ($item in $expected) {
            if ($item.Value -cnotmatch '^[0-9a-f]{64}$' -or
                $Release.sha256.PSObject.Properties.Name -cnotcontains $item.Name -or
                $Release.sha256.($item.Name) -cne $item.Value) { throw 'Snapshot/ZIP hash mismatch.' }
        }
    }

    function Invoke-StarterManagedBundle([string]$Directory, [string]$Target) {
        # Never use bootstrap here: it may install Python and register startup.
        $python = $null
        foreach ($candidate in @((Join-Path $env:LOCALAPPDATA 'Programs/Python/Python311/python.exe'), 'python.exe')) {
            $command = Get-Command $candidate -ErrorAction SilentlyContinue
            if ($command) {
                & $command.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' | Out-Host
                if ($LASTEXITCODE -eq 0) { $python = $command.Source; break }
            }
        }
        if (-not $python) { throw 'Python 3.11 이상을 사용자가 먼저 설치하고 다시 확인해 주세요. 자동 설치하지 않습니다.' }
        # Native preflight, immutable deployment and transactional connection updates
        # remain owned by the verified bundled install_sev.py.
        $script = 'scaffold.py'
        $arguments = @('--target', $Target, '--adopt', '--no-autostart')
        if ((Test-Path -LiteralPath (Join-Path $Target 'AGENTS.md') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $Target '.ai/models.yaml') -PathType Leaf)) {
            $script = 'install_sev.py'
            $arguments = @('--target', $Target, '--no-autostart')
        }
        & $python (Join-Path $Directory $script) @arguments | Out-Host
        if ($LASTEXITCODE -ne 0) { throw '설치가 실패했습니다. 기존 연결은 보존됩니다. 준비사항과 권한을 확인한 뒤 다시 실행해 주세요.' }
    }

    function Assert-StarterInstalled([string]$Target, [string]$Version) {
        $configPath = Assert-StarterPath (Join-Path $Target '.ai/sev.json')
        $config = [IO.File]::ReadAllText($configPath) | ConvertFrom-Json
        if ($config.version -cne $Version) { throw '설치 후 버전 확인에 실패했습니다.' }
        foreach ($key in @('python', 'service', 'state', 'runner', 'project_runner')) {
            if (-not $config.$key -or -not [IO.Path]::IsPathRooted($config.$key) -or
                -not (Test-Path -LiteralPath (Assert-StarterPath $config.$key) -PathType Leaf)) {
                throw "설치 후 필수 경로 확인에 실패했습니다: $key"
            }
        }
    }

    function Test-StarterEntryName([string]$Name) {
        if (-not $Name.StartsWith('universal-ai-starter/', [StringComparison]::Ordinal) -or
            $Name.Contains('\') -or $Name.Contains(':')) { throw "Unsafe ZIP path: $Name" }
        foreach ($part in $Name.Split('/')) {
            if (-not $part -or $part -in @('.', '..') -or $part -match '[<>"|?*\x00-\x1f]' -or
                $part -match '[ .]$' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
                throw "Unsafe ZIP path: $Name"
            }
        }
    }

    function Expand-VerifiedStarter([byte[]]$Bytes, [string]$Stage, $Snapshot = $null) {
        Add-Type -AssemblyName System.IO.Compression
        $stream = New-Object IO.MemoryStream(,$Bytes)
        $zip = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Read)
        try {
            # Validate the complete archive before writing any entry. This package contains only files.
            $entries = @{}
            [long]$total = 0
            if ($zip.Entries.Count -gt 256) { throw 'ZIP has too many entries.' }
            foreach ($entry in $zip.Entries) {
                Test-StarterEntryName $entry.FullName
                if ($entry.FullName -ne 'universal-ai-starter/SKILL.md' -and
                    $entry.FullName -match '(?i)(^|/)SKILL\.md$') { throw 'Unexpected nested discoverable skill.' }
                if ($entries.ContainsKey($entry.FullName)) { throw 'Duplicate ZIP path.' }
                if (($entry.ExternalAttributes -band 0x400) -or
                    (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'ZIP links are not allowed.' }
                $total += $entry.Length
                if ($total -gt 64MB) { throw 'ZIP exceeds the expected uncompressed size.' }
                $entries[$entry.FullName] = $entry
            }
            foreach ($name in $entries.Keys) {
                $parent = $name
                while ($parent.Contains('/')) {
                    $parent = $parent.Substring(0, $parent.LastIndexOf('/'))
                    if ($entries.ContainsKey($parent)) { throw 'Conflicting ZIP file/directory paths.' }
                }
            }
            $releaseEntry = $entries['universal-ai-starter/release.json']
            if (-not $releaseEntry -or $releaseEntry.Length -gt 1MB) { throw 'Missing/invalid release metadata.' }
            $reader = New-Object IO.StreamReader($releaseEntry.Open())
            try { $release = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            if ($release.version -ne '0.3.3' -or -not $release.sha256) { throw 'Expected starter release 0.3.3.' }
            if ($Snapshot) { Assert-StarterReleaseMatch $Snapshot $release }
            $hashes = @($release.sha256.PSObject.Properties)
            if ($hashes.Count -ne ($entries.Count - 1)) { throw 'Release manifest does not cover every ZIP file.' }
            $required = @('SKILL.md', 'scripts/bootstrap.ps1', 'scripts/scaffold.py', 'scripts/install_sev.py',
                'assets/runner/SKILL.template.md', 'assets/runner/run.py', 'assets/sev/setup_model.py',
                'assets/sev/sev_service.py', 'assets/sev/requirements.txt', 'assets/starter/AGENTS.md',
                'assets/starter/PROJECT.md', 'assets/starter/.ai/models.yaml')
            foreach ($name in $required) {
                if (-not $entries.ContainsKey("universal-ai-starter/$name")) { throw "Missing bundled asset: $name" }
            }
            $sha = [Security.Cryptography.SHA256]::Create()
            try {
                foreach ($property in $hashes) {
                    Test-StarterEntryName $property.Name
                    if ($property.Name -eq 'universal-ai-starter/release.json' -or
                        -not $entries.ContainsKey($property.Name) -or $property.Value -cnotmatch '^[0-9a-f]{64}$') {
                        throw 'Invalid release hash manifest.'
                    }
                    $entryStream = $entries[$property.Name].Open()
                    try { $digest = [BitConverter]::ToString($sha.ComputeHash($entryStream)).Replace('-', '').ToLowerInvariant() }
                    finally { $entryStream.Dispose() }
                    if ($digest -cne $property.Value) { throw "ZIP integrity check failed: $($property.Name)" }
                }
            } finally { $sha.Dispose() }
            $reader = New-Object IO.StreamReader($entries['universal-ai-starter/SKILL.md'].Open())
            try { $skillText = $reader.ReadToEnd() } finally { $reader.Dispose() }
            if ($skillText -notmatch '(?m)^name: universal-ai-starter\r?$') { throw 'Unexpected skill identity.' }
            foreach ($name in $entries.Keys) {
                $destination = [IO.Path]::GetFullPath((Join-Path $Stage $name))
                if (-not $destination.StartsWith($Stage.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
                    throw 'ZIP path escaped staging directory.'
                }
                $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
                $inputStream = $entries[$name].Open()
                $outputStream = [IO.File]::Open($destination, [IO.FileMode]::CreateNew)
                try { $inputStream.CopyTo($outputStream) }
                finally { $outputStream.Dispose(); $inputStream.Dispose() }
            }
        } finally { $zip.Dispose(); $stream.Dispose() }
    }

    # Select/cancel before ZIP download, skill changes or project writes.
    if ($Manager -and [string]::IsNullOrWhiteSpace($Target)) {
        [pscustomobject]@{schema=1; status='cancelled'; exitCode=2} | ConvertTo-Json -Compress
        $script:starterExitCode = 2
        return
    }
    $Target = Select-StarterTarget $Target
    if (-not $Target) { Write-Host 'Installation cancelled; no project files written.'; $script:starterExitCode = 2; return }
    $snapshot = $null
    if ($Manager) { $snapshot = Get-StarterSnapshot $SnapshotCommit $ExpectedVersion }
    $skills = Assert-StarterPath (Join-Path $HOME '.agents/skills')
    $runtime = Assert-StarterPath (Join-Path $HOME '.codex/sev')
    foreach ($protected in @($skills, $runtime, [IO.Path]::GetTempPath().TrimEnd('\'))) {
        if ($Target.TrimEnd('\') -eq $protected.TrimEnd('\') -or
            $Target.StartsWith($protected.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) -or
            $protected.StartsWith($Target.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Project folder must not overlap skills, shared runtime or temporary storage.'
        }
    }
    $bytes = Get-StarterPublicZip
    $stage = Assert-StarterPath (Join-Path ([IO.Path]::GetTempPath()) ('starter-' + [Guid]::NewGuid().ToString('N')))
    $installed = Join-Path $skills 'universal-ai-starter'
    $backup = Join-Path $skills ('universal-ai-starter.backup-' + [Guid]::NewGuid().ToString('N'))
    try {
        Expand-VerifiedStarter $bytes $stage $snapshot
        if ($Manager) {
            Invoke-StarterManagedBundle (Join-Path $stage 'universal-ai-starter/scripts') $Target
            Assert-StarterInstalled $Target $ExpectedVersion
            [pscustomobject]@{schema=1; status='installed'; exitCode=0; version=$ExpectedVersion; snapshot=$SnapshotCommit; target=$Target; autostart=$false; personalSkillReplaced=$false} | ConvertTo-Json -Compress
            return
        }
        $null = Assert-StarterPath $installed
        if (Test-Path -LiteralPath $installed) {
            if (-not (Test-Path -LiteralPath $installed -PathType Container)) { throw 'Installed skill path is not a directory.' }
            if (Get-ChildItem -LiteralPath $installed -Force -Recurse | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
                throw 'Existing skill contains links/reparse points; resolve them before retrying.'
            }
        }
        # Run the verified staged bundle before committing any personal skill change.
        # The installer checks the actual new venv in the native managed sandbox.
        $Target = Select-StarterTarget $Target
        $bootstrapDirectory = Join-Path $stage 'universal-ai-starter/scripts'
        $bootstrapText = [IO.File]::ReadAllText((Join-Path $bootstrapDirectory 'bootstrap.ps1'), [Text.Encoding]::UTF8)
        & ([scriptblock]::Create($bootstrapText)) -Target $Target -ScriptDirectory $bootstrapDirectory
        $null = [IO.Directory]::CreateDirectory($skills)
        if (Test-Path -LiteralPath $installed) { Move-Item -LiteralPath $installed -Destination $backup }
        try { Move-Item -LiteralPath (Join-Path $stage 'universal-ai-starter') -Destination $installed }
        catch {
            if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $installed }
            throw
        }
        # Preserve the old personal skill backup, including user customizations.
        if (Test-Path -LiteralPath $backup) { Write-Host "Previous skill preserved at $backup" }
        Write-Host "Starter 0.3.3 and SEV installed for $Target. Restart Codex to refresh skills."
    } catch {
        if (Test-Path -LiteralPath $backup) {
            if (Test-Path -LiteralPath $installed) {
                $failed = Join-Path $skills ('universal-ai-starter.failed-' + [Guid]::NewGuid().ToString('N'))
                Move-Item -LiteralPath $installed -Destination $failed
            }
            Move-Item -LiteralPath $backup -Destination $installed
        }
        throw
    } finally {
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
} $Target ([bool]$Manager) $SnapshotCommit $ExpectedVersion
} catch {
    $starterExitCode = 1
    if ($Manager) {
        # Do not serialize exception text: it may contain private paths or process output.
        [pscustomobject]@{schema=1; status='error'; exitCode=1; message='설치 또는 검증에 실패했습니다. 준비사항과 네트워크를 확인하고 다시 실행해 주세요.'} | ConvertTo-Json -Compress
        Write-Warning '관리기 설치 실패: Python 3.11+, Codex CLI 준비, 네트워크와 권한을 확인해 주세요. 자동 승격하지 않습니다.'
    } else { throw }
}
if ($Manager) { exit $starterExitCode }
