@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First-time setup is required.
    call INSTALL_APP.bat
    if errorlevel 1 exit /b 1
)

echo Starting the thesis allocation application...
echo Keep this window open while using the application.
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.headless false

if errorlevel 1 (
    echo.
    echo The application stopped with an error.
    pause
)

