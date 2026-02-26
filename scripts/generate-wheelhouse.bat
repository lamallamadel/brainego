@echo off
REM Generate offline wheelhouse for testing (Windows batch version)
REM Run this ONCE on a machine with Internet access
REM Then commit vendor\wheels\ to the repo

echo.
echo 🔧 Generating offline wheelhouse for brainego tests...
echo.
echo Requirements:
echo   - Python 3.11+ with pip
echo   - Internet access (this machine)
echo.

REM Use native Windows python
set PYTHON=python

REM Verify Python exists
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found!
    exit /b 1
)

echo ✅ Using Python: %PYTHON%
%PYTHON% --version
echo.

REM Verify pip is available
%PYTHON% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip not found in %PYTHON%
    exit /b 1
)

echo ✅ pip is available:
%PYTHON% -m pip --version
echo.

REM Create vendor directory
if not exist vendor\wheels mkdir vendor\wheels

echo 📦 Downloading wheels for requirements-test.txt (no platform constraints)...
%PYTHON% -m pip download ^
  --only-binary=:all: ^
  --no-deps ^
  -d vendor\wheels ^
  -r requirements-test.txt

if errorlevel 1 (
    echo ❌ First download failed
    exit /b 1
)

echo.
echo 📦 Downloading dependency wheels (recursive)...
%PYTHON% -m pip download ^
  --only-binary=:all: ^
  -d vendor\wheels ^
  -r requirements-test.txt

if errorlevel 1 (
    echo ⚠️  Some dependencies may not have wheels available
    echo    (This is OK - CI will handle source distributions)
)

echo.
echo ✅ Wheelhouse generated!
echo.
echo 📂 Contents:
dir vendor\wheels
echo.
echo 📝 Next steps:
echo   1. git add vendor/wheels/
echo   2. git commit -m "Add offline wheels"
echo   3. git push
echo.
echo ✨ CI will now use: --no-index --find-links=vendor/wheels
echo ✨ Zero network access in GitHub Actions!
