#!/bin/bash
# Generate offline wheelhouse for testing
# Run this ONCE on a machine with Internet access
# Then commit vendor/wheels/ to the repo

set -e

echo "🔧 Generating offline wheelhouse for brainego tests..."
echo ""
echo "Requirements:"
echo "  - Python 3.11+"
echo "  - pip with wheel support"
echo "  - Internet access (this machine)"
echo ""

# Create vendor directory
mkdir -p vendor/wheels

echo "📦 Downloading wheels for requirements-test.txt..."
python -m pip download \
  --python-version 311 \
  --platform manylinux_2_28_x86_64 \
  --only-binary=:all: \
  --no-deps \
  -d vendor/wheels \
  -r requirements-test.txt

echo ""
echo "📦 Downloading wheels for dependencies (recursive)..."
python -m pip download \
  --python-version 311 \
  --platform manylinux_2_28_x86_64 \
  --only-binary=:all: \
  -d vendor/wheels \
  -r requirements-test.txt

echo ""
echo "✅ Wheelhouse generated!"
echo ""
echo "Contents:"
ls -lh vendor/wheels/ | tail -20
echo ""
echo "Total size:"
du -sh vendor/wheels/
echo ""
echo "📝 Next steps:"
echo "  1. git add vendor/wheels/"
echo "  2. git commit -m 'Add offline wheels for test dependencies'"
echo "  3. git push"
echo ""
echo "✨ CI will now use: --no-index --find-links=vendor/wheels"
