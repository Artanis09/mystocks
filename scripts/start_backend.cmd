@echo off
setlocal
cd /d %~dp0\..

set PYTHON_EXE=.venv\Scripts\python.exe
if not exist %PYTHON_EXE% (
  echo [backend] Virtualenv not found: %PYTHON_EXE%
  echo [backend] Create it: python -m venv .venv
  echo [backend] Install deps: %PYTHON_EXE% -m pip install -r requirements.txt
  exit /b 1
)

echo [backend] Using python: %PYTHON_EXE%
%PYTHON_EXE% -c "import sys; print('[backend] sys.executable:', sys.executable)"

%PYTHON_EXE% -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

%PYTHON_EXE% update_stock_prices.py
