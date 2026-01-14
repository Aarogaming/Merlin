@echo off
setlocal

cd /d "%~dp0"

if defined PYTHON_EXE goto :verify_env_python
set PYTHON_EXE=

if exist ".venv\Scripts\python.exe" (
  set PYTHON_EXE=.venv\Scripts\python.exe
) else (
  where py >nul 2>nul
  if %ERRORLEVEL%==0 (
    py -3 -m venv .venv
    set PYTHON_EXE=.venv\Scripts\python.exe
  ) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
      python -m venv .venv
      set PYTHON_EXE=.venv\Scripts\python.exe
    )
  )
)

if "%PYTHON_EXE%"=="" (
  echo Python not found. Install Python 3.12+ from python.org or run:
  echo   winget install Python.Python.3.12
  exit /b 1
)

%PYTHON_EXE% -m pip install --upgrade pip
%PYTHON_EXE% -m pip install -r requirements.txt -r requirements-dev.txt
%PYTHON_EXE% -m pytest

pause
goto :eof

:verify_env_python
if not exist "%PYTHON_EXE%" (
  echo PYTHON_EXE was set but was not found at: %PYTHON_EXE%
  exit /b 1
)
