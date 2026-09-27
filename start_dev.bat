@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo DEVELOPMENT MODE - installs/updates Python packages on this PC.
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
python server.py
