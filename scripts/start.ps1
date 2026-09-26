$ErrorActionPreference = 'Stop'
$LebotProjectDir = Split-Path -Parent $PSScriptRoot
Set-Location $LebotProjectDir
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    & '.venv\Scripts\python.exe' -m pip install --upgrade pip
    & '.venv\Scripts\python.exe' -m pip install -e '.[documents,browser,secure-keys]'
    & '.venv\Scripts\python.exe' -m playwright install chromium
}
& '.venv\Scripts\python.exe' -m lebotclaw_harness web --open @args
