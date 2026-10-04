# Start Chamber Studio (the dashboard app) in the browser.
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File C:\Users\ixiat\Desktop\codex\chamberviz\run_studio.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "First run: creating the environment (a few minutes)..."
    python -m venv .venv
    # --use-feature=truststore: trust the Windows certificate store (needed with Avast HTTPS scanning)
    & $py -m pip install --use-feature=truststore --upgrade pip
    & $py -m pip install --use-feature=truststore -e ".[dashboard]" truststore
}

Write-Host "Starting Chamber Studio (press Ctrl+C here to stop)"
& $py -m chamberviz dashboard
