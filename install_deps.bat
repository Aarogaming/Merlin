@echo off
echo Installing Merlin Merlin System Dependencies...

:: Task 18: Create a script to install system dependencies
:: This script assumes Windows 11 with winget or manual installs

echo Checking for Python 3.10+...
python --version
if %errorlevel% neq 0 (
    echo Python not found. Please install Python 3.10 or higher.
    exit /b 1
)

echo Installing PortAudio (via winget)...
winget install -e --id PortAudio.PortAudio
if %errorlevel% neq 0 (
    echo Winget failed or PortAudio not found. Please install PortAudio manually for PyAudio.
)

echo Installing FFmpeg (via winget)...
winget install -e --id Gyan.FFmpeg
if %errorlevel% neq 0 (
    echo Winget failed or FFmpeg not found. Please install FFmpeg manually.
)

echo Installing Python dependencies...
pip install -r requirements.txt
pip install -r requirements-dev.txt

echo System dependencies installation complete.
pause
