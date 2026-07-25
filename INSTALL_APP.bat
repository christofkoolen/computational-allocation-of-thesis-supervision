@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python was not found.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
    echo During installation, select "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the private application environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :failed
)

echo Installing the thesis allocation application...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -e ".[app]"
if errorlevel 1 goto :failed

echo.
echo Installation completed successfully.
echo You can now double-click START_APP.bat.
pause
exit /b 0

:failed
echo.
echo Installation failed. Copy the error shown above when asking for help.
pause
exit /b 1

