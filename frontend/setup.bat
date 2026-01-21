@echo off
echo 🧙‍♂️ Merlin Frontend Setup
echo ==========================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Node.js is not installed. Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)

echo ✅ Node.js detected

REM Check if Rust is installed
cargo --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Rust/Cargo is not installed. Please install Rust from https://rustup.rs
    pause
    exit /b 1
)

echo ✅ Rust detected

REM Navigate to frontend directory
echo 📁 Working directory: %CD%

REM Install Node.js dependencies
echo.
echo 📦 Installing Node.js dependencies...
npm install

if %errorlevel% neq 0 (
    echo ❌ Failed to install Node.js dependencies
    pause
    exit /b 1
)

echo ✅ Node.js dependencies installed

REM Install Tauri CLI locally
echo.
echo 🔧 Installing Tauri CLI...
npm install --save-dev @tauri-apps/cli

echo ✅ Tauri CLI installed

REM Check TypeScript configuration
echo.
echo 🏗️  Testing build configuration...
npm run typecheck

if %errorlevel% neq 0 (
    echo ❌ TypeScript check failed
    pause
    exit /b 1
)

echo ✅ TypeScript configuration OK

REM Run linter
echo.
echo 🔍 Running linter...
npm run lint

if %errorlevel% neq 0 (
    echo ⚠️  Linter found issues (this is OK for initial setup)
)

echo.
echo 🎉 Setup completed successfully!
echo.
echo 🚀 Next steps:
echo    1. Start the Merlin backend server (on port 8000)
echo    2. Run: npm run tauri:dev
echo    3. The dashboard will open in a native window
echo.
echo 📖 For more information, see README.md
echo.
echo 🌟 Happy coding with Merlin!
pause