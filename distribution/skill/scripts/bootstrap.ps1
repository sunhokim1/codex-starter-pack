param([Parameter(Mandatory=$true)][string]$Target)
& (Join-Path $PSScriptRoot '../../../distribution/releases/0.4.0/universal-ai-starter/scripts/bootstrap.ps1') -Target $Target
