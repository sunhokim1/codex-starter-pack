# Public installer: irm https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/main/scripts/install_from_github.ps1 | iex
# Saved-file usage: .\install_from_github.ps1 [-Target 'C:\your\project']
& {
    param([string]$Target)
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

    function Get-StarterPublicZip {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $client = New-Object Net.WebClient
        try {
            # Pin this v0.3.1 installer to its verified release, avoiding branch-cache skew.
            $url = 'https://raw.githubusercontent.com/sunhokim1/codex-starter-pack/60541b99d8ce6c062567e1a69c4ef24169154be6/universal-ai-starter.zip'
            $bytes = $client.DownloadData($url)
            if ($bytes.Length -eq 0 -or $bytes.Length -gt 32MB) { throw 'Unexpected ZIP download size.' }
            return ,$bytes
        } finally { $client.Dispose() }
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

    function Expand-VerifiedStarter([byte[]]$Bytes, [string]$Stage) {
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
            if ($release.version -ne '0.3.1' -or -not $release.sha256) { throw 'Expected starter release 0.3.1.' }
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
    $Target = Select-StarterTarget $Target
    if (-not $Target) { Write-Host 'Installation cancelled; no project files written.'; return }
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
        Expand-VerifiedStarter $bytes $stage
        $null = Assert-StarterPath $installed
        if (Test-Path -LiteralPath $installed) {
            if (-not (Test-Path -LiteralPath $installed -PathType Container)) { throw 'Installed skill path is not a directory.' }
            if (Get-ChildItem -LiteralPath $installed -Force -Recurse | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
                throw 'Existing skill contains links/reparse points; resolve them before retrying.'
            }
        }
        $null = [IO.Directory]::CreateDirectory($skills)
        if (Test-Path -LiteralPath $installed) { Move-Item -LiteralPath $installed -Destination $backup }
        try { Move-Item -LiteralPath (Join-Path $stage 'universal-ai-starter') -Destination $installed }
        catch {
            if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $installed }
            throw
        }
        # Preserve the old personal skill backup, including user customizations.
        if (Test-Path -LiteralPath $backup) { Write-Host "Previous skill preserved at $backup" }
        # Recheck target immediately before bundled bootstrap writes anything.
        $Target = Select-StarterTarget $Target
        $bootstrapDirectory = Join-Path $installed 'scripts'
        $bootstrapText = [IO.File]::ReadAllText((Join-Path $bootstrapDirectory 'bootstrap.ps1'), [Text.Encoding]::UTF8)
        & ([scriptblock]::Create($bootstrapText)) -Target $Target -ScriptDirectory $bootstrapDirectory
        Write-Host "Starter 0.3.1 and SEV installed for $Target. Restart Codex to refresh skills."
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
} $(if ($args.Count -eq 0) { $null }
    elseif ($args.Count -eq 1) { $args[0] }
    elseif ($args.Count -eq 2 -and $args[0] -eq '-Target') { $args[1] }
    else { throw 'Usage: install_from_github.ps1 [-Target <project-folder>]' })
