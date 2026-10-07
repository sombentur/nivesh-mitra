# Starts the backend and the web app in two minimised windows, then opens your browser.
. "$PSScriptRoot\common.ps1"

if (-not (Test-Path (Join-Path $Web ".next\BUILD_ID"))) {
    Write-Host "NiveshMitra isn't set up yet. Double-click 'Setup NiveshMitra.bat' first." -ForegroundColor Red
    exit 1
}

function Start-Part([string]$Script, [int]$Port, [string]$Name) {
    if (Test-PortListening $Port) { Write-Ok "$Name already running"; return }
    Start-Process powershell -WindowStyle Minimized -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSScriptRoot\$Script`""
    )
    Write-Ok "$Name starting"
}

Write-Step "Starting NiveshMitra"
Start-Part "run-backend.ps1" 8000 "Backend"
Start-Part "run-web.ps1" 3000 "Web app"

Write-Step "Waiting for it to be ready"
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest "http://localhost:3000/api/health" -UseBasicParsing -TimeoutSec 3 | Out-Null
        Write-Ok "Ready"
        if (-not $env:NM_NO_BROWSER) { Start-Process "http://localhost:3000" }
        exit 0
    } catch { Start-Sleep -Seconds 2 }
}
Write-Host "It's taking longer than expected. Check the two minimised NiveshMitra windows for errors." -ForegroundColor Yellow
