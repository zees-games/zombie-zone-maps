# Fetch what this repository's content.lock.json names from the CDN (hash-checked, once; present files skipped).
# Thin wrapper: the one fetcher is dot-bootstrap\tools\fetch_lock.ps1 (options -Only, -Except, -Cdn, -List; see fetch_lock.sh's header).
# The CDN URL comes from -Cdn, $env:DOT_CDN_URL, or DOT_CDN_URL in dot-bootstrap\.env (one edit for every repo).
$ErrorActionPreference = 'Stop'
$boot = if ($env:DOT_BOOTSTRAP) { $env:DOT_BOOTSTRAP } else { Join-Path (Split-Path -Parent $PSScriptRoot) 'dot-bootstrap' }
$tool = Join-Path $boot 'tools\fetch_lock.ps1'
if (-not (Test-Path $tool)) { Write-Error 'fetch-content: dot-bootstrap is not beside this checkout; clone it or set DOT_BOOTSTRAP'; exit 2 }
& $tool (Join-Path $PSScriptRoot 'content.lock.json') -Root $PSScriptRoot @args
exit $LASTEXITCODE
