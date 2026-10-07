# Shared helpers for the NiveshMitra scripts.

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Web = Join-Path $Root "web"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }

# uv manages the project's own Python 3.12, separate from any Python already on this PC.
function Invoke-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) { & uv @args } else { & py -m uv @args }
    if ($LASTEXITCODE -ne 0) { throw "uv $($args -join ' ') failed" }
}

function Test-PortListening([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}
