@echo off
TITLE AAS Agent-Zero
echo [AAS] Initializing Runtime Lifecycle...

:: Use embedded python if available, otherwise system python
set "PY_CMD=python"
if exist "runtime\python\python.exe" set "PY_CMD=runtime\python\python.exe"

%PY_CMD% scripts\runtime_lifecycle.py start %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [AAS] Exited with error code %ERRORLEVEL%.
    pause
)
