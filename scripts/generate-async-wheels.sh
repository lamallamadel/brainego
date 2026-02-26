#!/bin/bash
# Generate offline wheelhouse for async testing (pytest-asyncio, anyio, etc.)
# Run this on a machine with Internet, commit vendor/wheels/ to repo

set -e

echo "🔧 Generating offline wheelhouse for async test dependencies..."
echo ""

PYTHON=${1:-python}

# Verify Python
if ! $PYTHON --version &>/dev/null; then
    echo "❌ Python not found: $PYTHON"
    exit 1
fi

echo "✅ Using: $PYTHON"
$PYTHON --version
echo ""

# Create directory
mkdir -p vendor/wheels

# Async test dependencies to download
ASYNC_DEPS=(
    "pytest-asyncio"
    "anyio"
    "pytest-anyio"
)

echo "📦 Downloading async test dependency wheels..."
for dep in "${ASYNC_DEPS[@]}"; do
    echo "  - $dep"
    $PYTHON -m pip download --only-binary=:all: --no-deps -d vendor/wheels "$dep" 2>/dev/null || echo "    ⚠️  Some variants may not have pure wheels"
done

echo ""
echo "📦 Downloading dependencies (recursive)..."
$PYTHON -m pip download --only-binary=:all: -d vendor/wheels "${ASYNC_DEPS[@]}"

echo ""
echo "✅ Async wheels generated in vendor/wheels/"
echo ""
echo "Contents:"
ls -lh vendor/wheels/ 2>/dev/null | tail -10 || echo "  (checking...)"
echo ""
echo "Next: git add vendor/wheels/ && git commit && git push"
