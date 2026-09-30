# Draw the fixed trade report charts (PNG files + one PDF) and open the folder.
#   powershell -ExecutionPolicy Bypass -File run_report.ps1                      (sample data)
#   powershell -ExecutionPolicy Bypass -File run_report.ps1 -Data "C:\data\trade_2026.xlsx"
param([string]$Data = "", [string]$Out = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "First run: creating the environment (a few minutes)..."
    python -m venv .venv
    & $py -m pip install --use-feature=truststore --upgrade pip
    & $py -m pip install --use-feature=truststore -e . truststore
}
$args = @("reports\trade_report.py")
if ($Data) { $args += $Data }
if (-not $Out) { $Out = "reports\output" }
$args += @("--out", $Out)
& $py @args
if ($LASTEXITCODE -eq 0) { Invoke-Item $Out }
