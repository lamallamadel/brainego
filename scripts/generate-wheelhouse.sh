#!/bin/bash
# Generate offline wheelhouse for testing
# Run this ONCE on a machine with Internet access
# Then commit vendor/wheels/ to the repo

set -e

echo "🔧 Generating offline wheelhouse for brainego tests..."
echo ""
echo "Requirements:"
echo "  - Python 3.11+ with pip"
echo "  - Internet access (this machine)"
echo ""

# On Windows/Git Bash, prefer 'python' (native) over 'python3' (WSL)
PYTHON=""

# Try 'python' first (Windows native Python)
if command -v python &> /dev/null; then
    PYTHON=python
# Fallback to 'python3' if available
elif command -v python3 &> /dev/null; then
    PYTHON=python3
else
    echo "❌ Python not found! Install Python 3.11+ first."
    exit 1
fi

echo "✅ Using Python: $PYTHON"
$PYTHON --version
echo ""

# Verify pip is available
if ! $PYTHON -m pip --version &> /dev/null; then
    echo "❌ pip not found in $PYTHON"
    echo "Run: $PYTHON -m ensurepip --upgrade"
    exit 1
fi

echo "✅ pip is available:"
$PYTHON -m pip --version
echo ""

# Create vendor directory
mkdir -p vendor/wheels

echo "📦 Downloading wheels for requirements-test.txt..."
$PYTHON -m pip download \
  --python-version 311 \
  --platform manylinux_2_28_x86_64 \
  --only-binary=:all: \
  --no-deps \
  -d vendor/wheels \
  -r requirements-test.txt

echo ""
echo "📦 Downloading dependency wheels (recursive)..."
$PYTHON -m pip download \
  --python-version 311 \
  --platform manylinux_2_28_x86_64 \
  --only-binary=:all: \
  -d vendor/wheels \
  -r requirements-test.txt

echo ""
echo "✅ Wheelhouse generated!"
echo ""
echo "📂 Contents:"
ls -lh vendor/wheels/ 2>/dev/null | head -15 || echo "  (checking...)"
echo ""
echo "📊 Total size:"
du -sh vendor/wheels/ 2>/dev/null || echo "  (computing...)"
echo ""
echo "📝 Next steps:"
echo "  1. git add vendor/wheels/"
echo "  2. git commit -m 'Add offline wheels'"
echo "  3. git push"
echo ""
echo "✨ CI will now use: --no-index --find-links=vendor/wheels"
echo "✨ Zero network access in GitHub Actions!"
