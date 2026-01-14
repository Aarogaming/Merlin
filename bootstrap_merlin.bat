@echo off
title MERLIN PRIME - BACKEND ASCENSION
echo Launching Merlin's consciousness (VENV Mode)...

:: Check for Virtual Environment
if exist .venv\Scripts\activate.bat (
    echo [INFO] Activating Virtual Environment...
    set PYTHON_CMD=.venv\Scripts\python.exe
) else (
    echo [WARNING] No .venv found. Using global python.
    set PYTHON_CMD=python
)

:: Start the API Server
start "Merlin API Server" cmd /k "%PYTHON_CMD% merlin_api_server.py"

:: Start the File Watcher (The Librarian)
start "Merlin Librarian Watcher" cmd /k "%PYTHON_CMD% merlin_watcher.py"

:: Start the Windows Overlay (The Orb)
start "Merlin Windows Overlay" cmd /k "cd /d \"../Maelstrom/Client\" && ..\Merlin\.venv\Scripts\python.exe merlin_overlay.py"

echo.
echo [SUCCESS] Backend systems are active.
echo Please ensure LM Studio is running on port 1234.
echo You may now press the 'RUN' button in Android Studio.
pause
