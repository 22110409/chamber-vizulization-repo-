# Draw the ACC trade charts (all sections, four designs, Arabic and English) and open the gallery.
# Run from anywhere:   powershell -ExecutionPolicy Bypass -File C:\Users\ixiat\Desktop\codex\chamberviz\run_charts.ps1
# Extra options are passed on, for example:   run_charts.ps1 --lang ar --designs navy_gold --only americas
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

& $py reports\acc_trade_charts.py @args
$gallery = Join-Path $PSScriptRoot "reports\output\acc_trade_charts\index.html"
if (Test-Path $gallery) { Start-Process $gallery }
