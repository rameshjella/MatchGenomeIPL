$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $RepoRoot "scripts\run_time_machine_app.py"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Runner)) {
    Write-Error "Could not find runner script at $Runner"
}

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $PythonCmd) {
        Write-Error "Python was not found. Activate your environment or install Python 3.10+ and retry."
    }
    $PythonExe = $PythonCmd.Source
}

Write-Host "[STARTUP] MatchGenomeIPL"
Write-Host "[ENV] Python executable: $PythonExe"
Write-Host "[RUN] Starting Time Machine app..."

& $PythonExe -c "import sys;import sqlite3" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Missing Python dependencies. Ensure sqlite3 support is available in this Python environment."
}

Push-Location $RepoRoot
try {
    & $PythonExe -u $Runner
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

