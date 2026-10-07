# Stops whatever is serving NiveshMitra's two local ports.
. "$PSScriptRoot\common.ps1"
foreach ($port in 8000, 3000) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Write-Host "NiveshMitra stopped." -ForegroundColor Green
