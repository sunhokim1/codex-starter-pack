# 0.4.0: 소스 설치·업데이트와 명시적 Rev 연결을 분리합니다.
[CmdletBinding()]
param([string]$Target, [string]$BundlePath, [string]$ArchivePath,
      [string]$RuntimeRoot, [string]$ConnectionFile, [switch]$Migrate,
      [switch]$FilesOnly, [switch]$Manager, [string]$SnapshotCommit,
      [string]$ExpectedVersion='0.4.0')
$ErrorActionPreference='Stop'
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
            $uri.Scheme -cne 'https' -or $uri.Host -cnotin @('raw.githubusercontent.com','api.github.com') -or
            $uri.Port -ne 443 -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or
            (($uri.Host -ceq 'api.github.com' -and $uri.AbsolutePath -cne '/repos/sunhokim1/codex-starter-pack/commits/main') -or ($uri.Host -ceq 'raw.githubusercontent.com' -and $uri.AbsolutePath -cnotmatch '^/sunhokim1/codex-starter-pack/[0-9a-f]{40}/distribution/releases/0\.4\.0/(universal-ai-starter\.zip|universal-ai-starter/release\.json)$'))) {
            throw '허용되지 않은 다운로드 URL입니다.'
        }
        return $uri
    }

    function Get-StarterBytes([string]$Url, [int]$Limit) {
        $null=Assert-StarterUrl $Url
        for ($attempt=0; $attempt -lt 2; $attempt++) {
            try { return ,(Receive-StarterBytes $Url $Limit) }
            catch { if ($attempt -eq 1) { throw } }
        }
    }
    function Receive-StarterBytes([string]$Url, [int]$Limit) {
        $uri = Assert-StarterUrl $Url
        if ($Limit -le 0 -or $Limit -gt 32MB) { throw 'Invalid download limit.' }
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $request = [Net.HttpWebRequest]::Create($uri)
        $request.AllowAutoRedirect = $false
        $request.UserAgent = 'Codex-Starter-Installer/0.4.0'
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

    function Resolve-StarterCommit {
        $latest=[Text.Encoding]::UTF8.GetString((Get-StarterBytes 'https://api.github.com/repos/sunhokim1/codex-starter-pack/commits/main' 1MB)) | ConvertFrom-Json
        if ($latest.sha -cnotmatch '^[0-9a-f]{40}$') { throw 'Invalid main commit.' }
        return $latest.sha
    }

    function Get-StarterSnapshot([string]$Commit, [string]$Version) {
        if ($Commit -cnotmatch '^[0-9a-f]{40}$' -or $Version -cne '0.4.0') { throw '지원하지 않는 snapshot 또는 배포 버전입니다.' }
        $url="https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$Commit/distribution/releases/0.4.0/universal-ai-starter/release.json"
        $release=[Text.Encoding]::UTF8.GetString((Get-StarterBytes $url 1MB)) | ConvertFrom-Json
        if ($release.version -cne $Version -or -not $release.sha256) { throw 'Snapshot metadata mismatch.' }
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
            if ($release.version -ne '0.4.0' -or -not $release.sha256) { throw 'Expected starter release 0.4.0.' }
            if ($Snapshot) { Assert-StarterReleaseMatch $Snapshot $release }
            $hashes = @($release.sha256.PSObject.Properties)
            if ($hashes.Count -ne ($entries.Count - 1)) { throw 'Release manifest does not cover every ZIP file.' }
            $required = @('SKILL.md', 'scripts/bootstrap.ps1', 'scripts/scaffold.py', 'scripts/install_rev.py',
                'assets/runner/SKILL.template.md', 'assets/runner/run.py', 'assets/rev/loader.py',
                'assets/rev/service.py', 'contracts/upstream.lock.json', 'assets/starter/AGENTS.md',
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


$stage=$null
try {
    if ($Manager -and ($RuntimeRoot -or $ConnectionFile -or $Migrate)) { throw '관리기 소스 설치에서는 실행 연결을 변경하지 않습니다.' }
    if (-not $Target) { throw '명시적 -Target이 필요합니다.' }
    if (-not $BundlePath -and -not $ArchivePath -and -not $SnapshotCommit) {
        $SnapshotCommit=Resolve-StarterCommit
    }
    if (([int][bool]$BundlePath + [int][bool]$ArchivePath + [int][bool]$SnapshotCommit) -ne 1) { throw 'BundlePath, ArchivePath, SnapshotCommit 중 하나만 사용하세요.' }
    $Target=Select-StarterTarget $Target
    $connect=[bool]($RuntimeRoot -or $ConnectionFile -or $Migrate)
    if ($connect -and (-not $RuntimeRoot -or -not $ConnectionFile -or $FilesOnly)) { throw '명시적 연결에는 RuntimeRoot와 ConnectionFile이 함께 필요합니다.' }
    $python=(Get-Command python.exe -ErrorAction Stop).Source
    if (-not $BundlePath) {
        $snapshot=$null
        if ($SnapshotCommit) {
            $snapshot=Get-StarterSnapshot $SnapshotCommit $ExpectedVersion
            $bytes=Get-StarterBytes "https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/$SnapshotCommit/distribution/releases/0.4.0/universal-ai-starter.zip" 32MB
        } else {
            $archive=Assert-StarterPath $ArchivePath
            if ((Get-Item -LiteralPath $archive).Length -gt 32MB) { throw 'ZIP too large.' }
            $bytes=[IO.File]::ReadAllBytes($archive)
        }
        $stage=Assert-StarterPath (Join-Path ([IO.Path]::GetTempPath()) ('starter-'+[Guid]::NewGuid().ToString('N')))
        Expand-VerifiedStarter $bytes $stage $snapshot
        $BundlePath=Join-Path $stage 'universal-ai-starter'
    }
    $BundlePath=Assert-StarterPath $BundlePath
    # Verify the full bundle before project writes, including local directory input.
    & $python -B -c 'import sys;sys.path.insert(0,sys.argv[1]);from install_rev import verify_bundle;from pathlib import Path;verify_bundle(Path(sys.argv[2]))' (Join-Path $BundlePath 'scripts') $BundlePath
    if ($LASTEXITCODE -ne 0) { throw '번들 무결성 오류' }
    if (-not $connect) {
        $arguments=@('-B',(Join-Path $BundlePath 'scripts/install_rev.py'),'--target',$Target,'--source-only')
        if ($SnapshotCommit) { $arguments+=@('--snapshot',$SnapshotCommit) }
        $lines=@(& $python @arguments)
        if ($LASTEXITCODE -ne 0) { throw '소스 설치를 중단했습니다. 기존 연결·설정·기록은 보존됩니다.' }
        $result=$lines[-1] | ConvertFrom-Json
        if (($result.version -cne $ExpectedVersion -and $result.source_status -cne 'newer') -or $result.source_status -cnotin @('installed','current','newer') -or $result.rev_status -cne 'preparation_needed') { throw 'Invalid source result.' }
        if ($Manager) {
            if ($result.source_status -ceq 'newer') { throw 'Stage downgrade refused.' }
            @{schema=1;status='installed';exitCode=0;version=$ExpectedVersion;snapshot=$SnapshotCommit;target=$Target;
              sourceStatus=$result.source_status;revStatus=$result.rev_status;autostart=$false;personalSkillReplaced=$false} | ConvertTo-Json -Compress
        } else { $lines }
    } else {
        $arguments=@('-B',(Join-Path $BundlePath 'scripts/install_rev.py'),'--target',$Target,'--runtime-root',$RuntimeRoot,'--connection-file',$ConnectionFile)
        if ($Migrate) { $arguments+='--migrate' }
        & $python @arguments
        if ($LASTEXITCODE -ne 0) { throw '연결을 중단했습니다. 기존 설정·기록을 보존하고 원인을 확인하세요.' }
    }
    exit 0
} catch { Write-Error $_ -ErrorAction Continue; exit 1 }
finally {
    if ($stage -and (Test-Path -LiteralPath $stage)) {
        $safe=Assert-StarterPath $stage
        $base=[IO.Path]::GetTempPath().TrimEnd('\')+'\'
        if (-not $safe.StartsWith($base,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($safe) -notmatch '^starter-[0-9a-f]{32}$') { throw 'Unsafe staging cleanup path.' }
        Remove-Item -LiteralPath $safe -Recurse -Force
    }
}
