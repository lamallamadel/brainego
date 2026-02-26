# Pytest Async Setup - Offline Wheels

## Problem

Tests with `@pytest.mark.asyncio` fixtures fail because:
- `pytest-asyncio` not installed (or wrong version)
- `asyncio_mode` not configured
- `anyio` / `pytest-anyio` missing

## Solution

### 1. Generate async wheels (one-time, on machine with Internet)

```bash
bash scripts/generate-async-wheels.sh
```

This downloads:
- `pytest-asyncio` ≥0.21.0
- `anyio` ≥3.7.0
- `pytest-anyio`

All wheels go to `vendor/wheels/`

### 2. Commit wheels

```bash
git add vendor/wheels/
git commit -m "Add async test wheels"
git push
```

### 3. CI installs offline

GitHub Actions workflow uses:
```bash
pip install --no-index --find-links=vendor/wheels -q -r requirements-test.txt
```

✅ Zero network, zero 403 errors.

## Configuration

`pytest.ini` already has:
```ini
[pytest]
asyncio_mode = auto
```

This is required for:
- `@pytest.mark.asyncio` to work
- Async fixtures to resolve correctly
- Event loop to be created automatically

## What this enables

✅ `@pytest.mark.asyncio` decorated tests
✅ `async def test_*()` functions
✅ `AsyncClient` from httpx
✅ Async fixtures with `@pytest_asyncio.fixture`
✅ Tests with `await` statements

## Troubleshooting

### "cannot collect test: asyncio_mode is not set"
→ Missing `asyncio_mode = auto` in `pytest.ini`
→ Already fixed ✅

### "No module named 'pytest_asyncio'"
→ Wheels not in `vendor/wheels/`
→ Run `bash scripts/generate-async-wheels.sh`
→ Commit and push

### "no running event loop"
→ Test not marked with `@pytest.mark.asyncio`
→ Add marker to async tests

## Example test

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_api_endpoint():
    """Async test with AsyncClient"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
```

## Files

| File | Purpose |
|------|---------|
| `requirements-test.txt` | Lists pytest-asyncio, anyio, pytest-anyio |
| `pytest.ini` | Sets `asyncio_mode = auto` |
| `vendor/wheels/` | Pre-downloaded .whl files |
| `scripts/generate-async-wheels.sh` | Generate wheels script |

---

**Offline async testing is now configured!** ✅
