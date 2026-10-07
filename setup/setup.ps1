# NiveshMitra one-time setup. Safe to run again (for example after an update).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\common.ps1"

try {
    Write-Step "Checking Python"
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Python isn't installed. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run setup again."
    }
    Write-Ok (& py --version)

    Write-Step "Installing uv (keeps NiveshMitra's Python separate from yours)"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        & py -m pip install --user --quiet --upgrade uv
        if ($LASTEXITCODE -ne 0) { throw "Could not install uv" }
    }
    Invoke-Uv --version

    Write-Step "Installing the backend (downloads Python 3.12 the first time; a few minutes)"
    Invoke-Uv --directory "$Backend" sync

    Write-Step "Preparing the database"
    Invoke-Uv --directory "$Backend" run python -c "from app.db.migrate import upgrade_to_head; upgrade_to_head(); print('    database ready')"

    Write-Step "Self-check (automated tests)"
    Invoke-Uv --directory "$Backend" run pytest -q

    Write-Step "Checking Node.js"
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js isn't installed. Install the LTS version from https://nodejs.org/, then run setup again."
    }
    $nodeMajor = [int]((& node --version).TrimStart("v").Split(".")[0])
    if ($nodeMajor -lt 20) { throw "Node.js 20 or newer is needed (you have $(& node --version)). Install the LTS version from https://nodejs.org/." }
    Write-Ok (& node --version)

    Write-Step "Installing the web app"
    & npm --prefix "$Web" ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

    Write-Step "Building the web app"
    & npm --prefix "$Web" run build
    if ($LASTEXITCODE -ne 0) { throw "Web build failed" }

    Write-Host "`nSetup complete. Double-click 'Start NiveshMitra.bat' to open the app." -ForegroundColor Green
}
catch {
    Write-Host "`nSetup stopped: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
