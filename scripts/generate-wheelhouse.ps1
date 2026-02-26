# Generate offline wheelhouse for testing (Windows PowerShell version)
# Run this ONCE on a machine with Internet access
# Then commit vendor/wheels/ to the repo

Write-Host "🔧 Generating offline wheelhouse for brainego tests..." -ForegroundColor Cyan
Write-Host ""
Write-Host "Requirements:" -ForegroundColor Cyan
Write-Host "  - Python 3.11+ with pip" -ForegroundColor Gray
Write-Host "  - Internet access (this machine)" -ForegroundColor Gray
Write-Host ""

# Use native Windows python
$PYTHON = "python"

# Verify Python exists
$pythonCheck = & $PYTHON --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Python not found!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Using Python: $PYTHON" -ForegroundColor Green
Write-Host $pythonCheck
Write-Host ""

# Verify pip is available
$pipCheck = & $PYTHON -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ pip not found in $PYTHON" -ForegroundColor Red
    exit 1
}

Write-Host "✅ pip is available:" -ForegroundColor Green
Write-Host $pipCheck
Write-Host ""

# Create vendor directory
if (-not (Test-Path "vendor/wheels")) {
    New-Item -ItemType Directory -Path "vendor/wheels" -Force | Out-Null
}

Write-Host "📦 Downloading wheels for requirements-test.txt..." -ForegroundColor Cyan
& $PYTHON -m pip download `
  --python-version 311 `
  --platform manylinux_2_28_x86_64 `
  --only-binary=:all: `
  --no-deps `
  -d vendor/wheels `
  -r requirements-test.txt

Write-Host ""
Write-Host "📦 Downloading dependency wheels (recursive)..." -ForegroundColor Cyan
& $PYTHON -m pip download `
  --python-version 311 `
  --platform manylinux_2_28_x86_64 `
  --only-binary=:all: `
  -d vendor/wheels `
  -r requirements-test.txt

Write-Host ""
Write-Host "✅ Wheelhouse generated!" -ForegroundColor Green
Write-Host ""
Write-Host "📂 Contents:" -ForegroundColor Cyan
Get-ChildItem vendor/wheels -ErrorAction SilentlyContinue | Select-Object -First 15 | ForEach-Object { "{0} ({1})" -f $_.Name, $_.Length }
Write-Host ""
Write-Host "📊 Total size:" -ForegroundColor Cyan
$size = (Get-ChildItem vendor/wheels -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host "  $($size.ToString('F2')) MB"
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Cyan
Write-Host "  1. git add vendor/wheels/" -ForegroundColor Gray
Write-Host "  2. git commit -m 'Add offline wheels'" -ForegroundColor Gray
Write-Host "  3. git push" -ForegroundColor Gray
Write-Host ""
Write-Host "✨ CI will now use: --no-index --find-links=vendor/wheels" -ForegroundColor Green
Write-Host "✨ Zero network access in GitHub Actions!" -ForegroundColor Green
