@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   SBDF Dashboard - Windows Portable Builder
echo ============================================================
echo.
echo This script is ONLY for the build/development PC.
echo The generated portable folder will not run pip or install Python.
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python launcher "py" was not found on this BUILD PC.
  echo Install Python on the build PC only, then run this file again.
  pause
  exit /b 1
)

if not exist ".build-venv\Scripts\python.exe" (
  echo [1/5] Creating isolated build environment...
  py -3.12 -m venv .build-venv 2>nul
  if errorlevel 1 py -3 -m venv .build-venv
  if errorlevel 1 goto :failed
) else (
  echo [1/5] Reusing existing build environment...
)

call ".build-venv\Scripts\activate.bat"
if errorlevel 1 goto :failed

echo [2/5] Installing build dependencies on this PC...
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install -r requirements.txt "pyinstaller>=6,<7"
if errorlevel 1 goto :failed

echo [3/5] Building portable Windows application...
if exist build rmdir /s /q build
if exist "dist\SBDF-Dashboard" rmdir /s /q "dist\SBDF-Dashboard"
python -m PyInstaller --clean --noconfirm SBDFDashboard.spec
if errorlevel 1 goto :failed

echo [4/5] Preparing portable folder...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0package_portable.ps1"
if errorlevel 1 goto :failed

echo [5/5] Finished.
echo.
echo ============================================================
echo BUILD COMPLETE
echo ============================================================
echo Portable folder:
echo   %CD%\dist\SBDF-Dashboard
echo.
echo Portable ZIP:
echo   %CD%\dist\SBDF-Dashboard-Portable.zip
echo.
echo Copy the portable folder/ZIP to the target Windows PC.
echo The target PC does NOT need Python, pip, or package installation.
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] Portable build failed. Review the messages above.
pause
exit /b 1
