param([Parameter(Mandatory=$true)][string]$Target, [string]$ScriptDirectory=$PSScriptRoot)
$ErrorActionPreference='Stop'
# Python, model, authentication and startup are never installed implicitly.
& python (Join-Path $ScriptDirectory 'scaffold.py') --target $Target --adopt --files-only
if ($LASTEXITCODE -ne 0) { throw '템플릿 준비 실패' }
Write-Host 'starter 소스·클라이언트를 준비했습니다. Rev 환경·모델·서비스와 명시적 실행 연결은 별도로 준비하세요.'
