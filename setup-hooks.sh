#!/bin/bash
#
# Setup script to install Git hooks
#

set -e

echo "🔧 Setting up Git hooks..."
echo ""

# Check if .githooks directory exists
if [ ! -d ".githooks" ]; then
    echo "❌ Error: .githooks directory not found"
    echo "Are you in the project root directory?"
    exit 1
fi

# Configure Git to use .githooks directory
git config core.hooksPath .githooks

# Make hooks executable
chmod +x .githooks/*

echo "✅ Git hooks installed successfully!"
echo ""
echo "The following hooks are now active:"
for hook in .githooks/*; do
    if [ -f "$hook" ]; then
        basename "$hook"
    fi
done
echo ""
echo "Pre-push hook will run 'make ci-lint' before each push."
echo "To bypass (not recommended), use: git push --no-verify"
echo ""
