#!/bin/bash
# Generate offline wheelhouse for testing
# Run this ONCE on a machine with Internet access
# Then commit vendor/wheels/ to the repo

set -e

echo "🔧 Generating offline wheelhouse for brainego tests..."
echo ""
echo "Requirements:"
echo "  - Python 3.11+ (available as 'python' or 'python3')"
echo "  - pip with wheel support"
echo "  - Internet access (this machine)"
echo ""

# Detect Python command
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "❌ Python not found! Install Python 3.11+ first."
    exit 1
fi

echo "✅ Using Python: $PYTHON"
$PYTHON --version
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
echo "Contents (last 20 files):"
ls -lh vendor/wheels/ 2>/dev/null | tail -20 || echo "  (vendor/wheels created)"
echo ""
echo "Total size:"
du -sh vendor/wheels/ 2>/dev/null || echo "  (0 bytes - empty placeholder)"
echo ""
echo "📝 Next steps:"
echo "  1. git add vendor/wheels/"
echo "  2. git commit -m 'Add offline wheels'"
echo "  3. git push"
echo ""
echo "✨ CI will now use: --no-index --find-links=vendor/wheels"
