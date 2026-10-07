. "$PSScriptRoot\common.ps1"
$Host.UI.RawUI.WindowTitle = "NiveshMitra backend - keep this window open"
Write-Host "NiveshMitra backend is running. Close this window (or run 'Stop NiveshMitra.bat') to stop it." -ForegroundColor Cyan
Invoke-Uv --directory "$Backend" run uvicorn app.main:app --host 127.0.0.1 --port 8000
