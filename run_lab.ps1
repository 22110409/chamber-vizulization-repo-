# Start the chamberviz Lab (creates its own environment the first time).
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File run_lab.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "First run: creating the lab environment (a few minutes)..."
    python -m venv .venv
    # --use-feature=truststore: trust the Windows certificate store (needed with Avast HTTPS scanning)
    & $py -m pip install --use-feature=truststore --upgrade pip
    & $py -m pip install --use-feature=truststore -e . gradio truststore
}

Write-Host "Starting the Lab (the address is printed below; press Ctrl+C here to stop)"
& $py lab\app.py
