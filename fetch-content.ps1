# Fetch what this repository's content.lock.json names from the CDN (hash-checked, once; present files skipped).
# Thin wrapper: the one fetcher is dot-bootstrap\tools\fetch_lock.ps1 (options -Only, -Except, -Cdn, -List; see fetch_lock.sh's header).
# The CDN URL comes from -Cdn, $env:GS_CDN_URL, or GS_CDN_URL in dot-bootstrap\.env (one edit for every repo).
$ErrorActionPreference = 'Stop'
foreach ($e in Get-ChildItem env:DOT_*) { $g = 'GS_' + $e.Name.Substring(4); if (-not (Test-Path "env:$g")) { Set-Item "env:$g" $e.Value; if (-not $env:GS_QUIET_DEPRECATION) { [Console]::Error.WriteLine("WARN: $($e.Name) is deprecated, use $g") } } }  # old DOT_* names still work
$boot = if ($env:GS_BOOTSTRAP) { $env:GS_BOOTSTRAP } else { Join-Path (Split-Path -Parent $PSScriptRoot) 'dot-bootstrap' }
$tool = Join-Path $boot 'tools\fetch_lock.ps1'
if (-not (Test-Path $tool)) { Write-Error 'fetch-content: dot-bootstrap is not beside this checkout; clone it or set GS_BOOTSTRAP'; exit 2 }
& $tool (Join-Path $PSScriptRoot 'content.lock.json') -Root $PSScriptRoot @args
exit $LASTEXITCODE
