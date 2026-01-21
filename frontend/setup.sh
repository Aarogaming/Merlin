#!/bin/bash

# Merlin Frontend Setup Script
# This script sets up the development environment for the Merlin Frontend Dashboard

echo "🧙‍♂️ Merlin Frontend Setup"
echo "=========================="
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ from https://nodejs.org"
    exit 1
fi

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "❌ Node.js version 18+ is required. Current version: $(node -v)"
    exit 1
fi

echo "✅ Node.js $(node -v) detected"

# Check if Rust is installed
if ! command -v cargo &> /dev/null; then
    echo "❌ Rust/Cargo is not installed. Please install Rust from https://rustup.rs"
    exit 1
fi

echo "✅ Rust $(cargo --version | cut -d' ' -f2) detected"

# Navigate to frontend directory
cd "$(dirname "$0")"
echo "📁 Working directory: $(pwd)"

# Install Node.js dependencies
echo ""
echo "📦 Installing Node.js dependencies..."
npm install

if [ $? -ne 0 ]; then
    echo "❌ Failed to install Node.js dependencies"
    exit 1
fi

echo "✅ Node.js dependencies installed"

# Install Tauri CLI locally if not already installed
echo ""
echo "🔧 Installing Tauri CLI..."
npm install --save-dev @tauri-apps/cli

echo "✅ Tauri CLI installed"

# Check if we can build
echo ""
echo "🏗️  Testing build configuration..."
npm run typecheck

if [ $? -ne 0 ]; then
    echo "❌ TypeScript check failed"
    exit 1
fi

echo "✅ TypeScript configuration OK"

# Run linter
echo ""
echo "🔍 Running linter..."
npm run lint

if [ $? -ne 0 ]; then
    echo "⚠️  Linter found issues (this is OK for initial setup)"
fi

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "🚀 Next steps:"
echo "   1. Start the Merlin backend server (on port 8000)"
echo "   2. Run: npm run tauri:dev"
echo "   3. The dashboard will open in a native window"
echo ""
echo "📖 For more information, see README.md"
echo ""
echo "🌟 Happy coding with Merlin!"