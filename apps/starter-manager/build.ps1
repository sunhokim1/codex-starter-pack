[CmdletBinding()]
param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist'))
$ErrorActionPreference = 'Stop'
try {
    $compiler = 'C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw '로컬 .NET Framework C# 컴파일러를 찾을 수 없습니다.' }
    $null = New-Item -ItemType Directory -Force -Path $OutputDirectory
    $sources = @('Core.cs', 'WindowsBoundary.cs', 'App.cs', 'AppDiagnostics.cs') | ForEach-Object { Join-Path $PSScriptRoot $_ }
    $references = @('/r:System.Web.Extensions.dll', '/r:System.Management.dll', '/r:System.Security.dll', '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll')
    & $compiler /nologo /target:winexe /main:StarterManager.Program /optimize+ /utf8output @references "/out:$(Join-Path $OutputDirectory 'CodexStarterManager.exe')" @sources
    if ($LASTEXITCODE -ne 0) { throw '관리기 EXE 빌드에 실패했습니다.' }
    Write-Output "관리기 빌드 완료: $(Join-Path $OutputDirectory 'CodexStarterManager.exe')"
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
