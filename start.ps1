param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8080,
    [switch]$Lan
)

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

if ($Lan.IsPresent) {
    $BindHost = "0.0.0.0"
}

$env:MATCHGENOME_HOST = $BindHost
$env:MATCHGENOME_PORT = [string]$Port

Write-Host "[RUN] Starting Time Machine app on $($env:MATCHGENOME_HOST):$($env:MATCHGENOME_PORT)..."

if ($env:MATCHGENOME_HOST -eq "0.0.0.0") {
    $ipv4 = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" } |
        Select-Object -First 1 -ExpandProperty IPAddress)
    if ($ipv4) {
        Write-Host "[LAN] Open from another laptop: http://${ipv4}:$($env:MATCHGENOME_PORT)"
    } else {
        Write-Host "[LAN] Host is exposed on all interfaces. Use this machine's IPv4 address with port $($env:MATCHGENOME_PORT)."
    }
}

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

