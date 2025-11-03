#!/bin/bash
# Quick Start Script for Playwright Tests
# Installs dependencies and runs tests

set -e  # Exit on error

echo "🎭 MVidarr Playwright Test Suite - Quick Start"
echo "=============================================="
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

echo "✅ Node.js version: $(node --version)"
echo ""

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install npm first."
    exit 1
fi

echo "✅ npm version: $(npm --version)"
echo ""

# Install dependencies
echo "📦 Installing npm dependencies..."
npm install

echo ""
echo "🎭 Installing Playwright browsers..."
npx playwright install

echo ""
echo "=============================================="
echo "✅ Setup complete!"
echo ""
echo "Available commands:"
echo "  npm test              - Run all tests"
echo "  npm run test:headed   - Run tests with browser visible"
echo "  npm run test:debug    - Run tests in debug mode"
echo "  npm run test:ui       - Run tests in UI mode"
echo "  npm run test:auth     - Run authentication tests only"
echo "  npm run test:pages    - Run page tests only"
echo "  npm run test:api      - Run API tests only"
echo "  npm run report        - View HTML test report"
echo ""
echo "📚 See README.md for full documentation"
echo ""

# Ask if user wants to run tests now
read -p "Do you want to run tests now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🧪 Running Playwright tests..."
    npm test
fi

echo ""
echo "🎉 All done!"
