@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=C:\Users\guoguo\.workbuddy-ai\binaries\python\envs\default\Scripts\python.exe"

if not exist "%PY%" (
  echo Python env not found: %PY%
  pause
  exit /b 1
)

"%PY%" run_daily.py
if errorlevel 1 (
  echo.
  echo Update failed. See messages above.
  pause
  exit /b 1
)

start "" "%~dp0site\index.html"
