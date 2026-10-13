param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
$starterPython = $null
foreach ($starterCandidate in @((Join-Path $env:LOCALAPPDATA 'Programs/Python/Python311/python.exe'), 'python.exe')) {
    if (Get-Command $starterCandidate -ErrorAction SilentlyContinue) {
        & $starterCandidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
        if ($LASTEXITCODE -eq 0) { $starterPython = $starterCandidate; break }
    }
}
if (-not $starterPython) {
    & winget install --id Python.Python.3.11 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed; install Python 3.11+ and retry.' }
    $starterPython = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python311/python.exe'
    if (-not (Test-Path -LiteralPath $starterPython)) { throw 'Python installed at an unexpected path; provide its path to scaffold.py.' }
}
& $starterPython (Join-Path $PSScriptRoot 'scaffold.py') --target $Target
if ($LASTEXITCODE -ne 0) { throw 'Starter application incomplete. Preserve conflicting project files and run install_sev.py after merging.' }
