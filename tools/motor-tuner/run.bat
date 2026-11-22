@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [DM Motor Tuner] Creating Python virtual environment...
    py -3 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import PySide6" 2>nul
if errorlevel 1 (
    echo [DM Motor Tuner] Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" app.py %*
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo [DM Motor Tuner] Failed to start. Check Python 3.11+ and network access.
pause
exit /b 1
