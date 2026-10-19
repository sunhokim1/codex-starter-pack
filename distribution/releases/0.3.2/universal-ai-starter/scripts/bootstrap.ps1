param([Parameter(Mandatory=$true)][string]$Target, [string]$ScriptDirectory = $PSScriptRoot)
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
if ((Test-Path -LiteralPath (Join-Path $Target 'AGENTS.md') -PathType Leaf) -and
    (Test-Path -LiteralPath (Join-Path $Target '.ai/models.yaml') -PathType Leaf)) {
    & $starterPython (Join-Path $ScriptDirectory 'install_sev.py') --target $Target
} else {
    & $starterPython (Join-Path $ScriptDirectory 'scaffold.py') --target $Target --adopt
}
if ($LASTEXITCODE -ne 0) { throw 'Starter/SEV installation failed. Existing project files were preserved; merge conflicting core files and retry.' }
