[CmdletBinding()]
param(
    [string]$BinaryPath = (Join-Path $PSScriptRoot 'dist/CodexStarterManager.exe'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist')
)
$ErrorActionPreference = 'Stop'
$temporary = $null
try {
    Add-Type -AssemblyName System.IO.Compression
    $null = New-Item -ItemType Directory -Force -Path $OutputDirectory
    $output = (Resolve-Path -LiteralPath $OutputDirectory).Path
    $binary = (Resolve-Path -LiteralPath $BinaryPath).Path
    if ([Diagnostics.FileVersionInfo]::GetVersionInfo($binary).FileVersion -ne '0.1.0.0') {
        throw '앱 0.1.0 빌드가 필요합니다.'
    }
    # Explicit allowlist: never enumerate the repository, diagnostics or user configuration.
    $payload = [ordered]@{
        'CodexStarterManager.exe' = [IO.File]::ReadAllBytes($binary)
        'README.md' = [IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'README.md'))
    }
    $temporary = Join-Path $output ('app-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew)
    try {
        $archive = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
        try {
            foreach ($name in $payload.Keys) {
                $entry = $archive.CreateEntry($name, [IO.Compression.CompressionLevel]::Optimal)
                $entry.LastWriteTime = [DateTimeOffset]::new(2020, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
                $content = $entry.Open()
                try { $content.Write($payload[$name], 0, $payload[$name].Length) } finally { $content.Dispose() }
            }
        } finally { $archive.Dispose() }
    } finally { $stream.Dispose() }
    $zip = Join-Path $output 'CodexStarterManager-0.1.0-win.zip'
    Move-Item -LiteralPath $temporary -Destination $zip -Force
    $temporary = $null
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $files = @($payload.Keys | ForEach-Object {
            [ordered]@{ path = $_; bytes = $payload[$_].Length; sha256 = ([BitConverter]::ToString($sha.ComputeHash($payload[$_]))).Replace('-', '').ToLowerInvariant() }
        })
    } finally { $sha.Dispose() }
    $manifest = [ordered]@{
        appVersion = '0.1.0'
        archive = [IO.Path]::GetFileName($zip)
        archiveSha256 = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        files = $files
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $output 'artifacts.json'), ($manifest | ConvertTo-Json -Depth 5), $utf8)
    Write-Output "앱 패키지 완료: $zip"
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    # Only this invocation's known temporary file, never a recursive directory cleanup.
    if ($temporary -and (Test-Path -LiteralPath $temporary)) { Remove-Item -LiteralPath $temporary }
}
