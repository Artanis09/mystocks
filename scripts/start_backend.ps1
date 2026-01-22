$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  Write-Error "Virtualenv not found at $python. Create it first (python -m venv .venv) and install deps (pip install -r requirements.txt)."
  exit 1
}

Write-Host "[backend] Using python: $python"
& $python -c "import sys; print('[backend] sys.executable:', sys.executable)"

# Optional: ensure deps are installed
& $python -m pip install -r (Join-Path $root 'requirements.txt')

& $python (Join-Path $root 'update_stock_prices.py')
