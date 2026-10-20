[CmdletBinding()]
param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'bin'))
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw '로컬 .NET Framework C# 컴파일러를 찾을 수 없습니다.' }
$null = New-Item -ItemType Directory -Force -Path $OutputDirectory
$references = @('/r:System.Web.Extensions.dll', '/r:System.Management.dll', '/r:System.Security.dll')
$sources = @((Join-Path $PSScriptRoot 'Core.cs'), (Join-Path $PSScriptRoot 'WindowsBoundary.cs'))
& $compiler /nologo /target:library /optimize+ @references "/out:$(Join-Path $OutputDirectory 'StarterManager.Core.dll')" @sources
if ($LASTEXITCODE -ne 0) { throw '코어 라이브러리 빌드에 실패했습니다.' }
& $compiler /nologo /target:exe /optimize+ @references "/r:$(Join-Path $OutputDirectory 'StarterManager.Core.dll')" "/out:$(Join-Path $OutputDirectory 'StarterManager.CoreTests.exe')" (Join-Path $PSScriptRoot 'CoreSelfTest.cs')
if ($LASTEXITCODE -ne 0) { throw '코어 self-test 빌드에 실패했습니다.' }
Write-Output "코어 빌드 완료: $OutputDirectory"
