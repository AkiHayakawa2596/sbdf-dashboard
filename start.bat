@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "SBDFDashboard.exe" (
  echo ============================================================
  echo SBDF Dashboard portable executable was not found.
  echo ============================================================
  echo.
  echo This launcher performs NO installation.
  echo.
  echo If you are on the development/build PC, run:
  echo   build_portable.bat
  echo.
  echo Then deploy the generated dist\SBDF-Dashboard folder.
  echo.
  pause
  exit /b 1
)

echo Starting SBDF Dashboard...
start "SBDF Dashboard Server" /min "%~dp0SBDFDashboard.exe"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8080/"
exit /b 0
