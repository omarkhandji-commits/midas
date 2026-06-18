@echo off
setlocal
title MIDAS Launcher

cd /d "%~dp0"

echo.
echo MIDAS local launcher
echo --------------------
echo This window installs/starts MIDAS locally, then opens the dashboard.
echo Keep it open while you use MIDAS. Close it to stop the server.
echo.

set "PY_CMD="
where py >nul 2>nul
if %ERRORLEVEL%==0 set "PY_CMD=py -3.11"
if not defined PY_CMD (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo Python 3.11+ was not found.
  echo Install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo MIDAS needs Python 3.11 or newer.
  echo Install the current Python version, then double-click this file again.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating a private MIDAS Python environment...
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto fail
)

echo Installing/updating MIDAS dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto fail

".venv\Scripts\python.exe" -m pip install -e ".[web,llm,multimodal,telegram,sheets,docs]"
if errorlevel 1 goto fail

echo Preparing local state...
".venv\Scripts\midas.exe" setup
if errorlevel 1 goto fail

echo.
echo Starting MIDAS...
echo Your browser should open automatically. If it does not, copy the Direct link below.
echo.
".venv\Scripts\midas.exe" dashboard --host 127.0.0.1 --port 8765 --base-dir . --show-link
exit /b 0

:fail
echo.
echo MIDAS could not start.
echo Most common causes: no internet during first install, Python too old, or antivirus blocking the local environment.
echo Send the last 20 lines of this window when asking for help.
pause
exit /b 1
