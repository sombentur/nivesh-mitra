. "$PSScriptRoot\common.ps1"
$Host.UI.RawUI.WindowTitle = "NiveshMitra web app - keep this window open"
Write-Host "NiveshMitra web app is running at http://localhost:3000" -ForegroundColor Cyan
& npm --prefix "$Web" run start
