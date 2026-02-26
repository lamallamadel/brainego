# AGENTS.md - Rules & Workflows

⚠️ **CRITICAL: Read CONTRATS.md first**

This file defines how agents (Codex, humans, CI) interact with brainego.

👉 **The law of brainego is in CONTRATS.md** - all invariants, responsibilities, and non-negotiable rules.

This AGENTS.md is the operational reference for setup, commands, and style.

---

## Codex Dependency Management (CRITICAL)

**When Codex generates tests that need new dependencies:**

1. **Codex declares the dependency explicitly in code comments:**
   ```python
   # Needs: httpx>=0.25.1
   # Needs: anyio>=3.7.0
   
   import httpx
   import anyio
   ```

2. **Codex does NOT attempt `pip install`** - it requests in comments only

3. **Human/Operator adds to `requirements-test.txt` and generates wheels:**
   ```bash
   echo "httpx>=0.25.1" >> requirements-test.txt
   python -m pip download -d vendor/wheels httpx anyio
   git add vendor/wheels/ requirements-test.txt
   git commit -m "Add offline wheels: httpx, anyio"
   git push
   ```

4. **Codex can now test locally using offline wheels:**
   ```bash
   # Install from offline wheelhouse (no network, no pip install online)
   python -m pip install --no-index --find-links=vendor/wheels -q -r requirements-test.txt
   
   # Run tests
   pytest tests/unit/ -v
   ```

**Key Rules:**
- ✅ Codex generates tests + declares `# Needs: package>=version`
- ✅ Codex uses `pip install --no-index --find-links=vendor/wheels`
- ❌ Codex never does `pip install package` (online pip forbidden in Codex)
- ❌ Codex never modifies `vendor/wheels/` directly
- ✅ Operator manages wheelhouse generation and commits

**Workflow Example:**

Codex generates test file:
```python
# tests/unit/test_http_client.py
# Needs: httpx>=0.25.1

import httpx
import pytest

@pytest.mark.unit
async def test_http_client():
    async with httpx.AsyncClient() as client:
        # test code
```

Operator responds:
```bash
# Add to requirements
echo "httpx>=0.25.1" >> requirements-test.txt

# Generate offline wheels
python -m pip download -d vendor/wheels httpx

# Commit
git add vendor/wheels/ requirements-test.txt
git commit -m "Add httpx wheels"
git push
```

Codex continues:
```bash
# Install from wheelhouse (no internet)
pip install --no-index --find-links=vendor/wheels -q -r requirements-test.txt

# Tests now pass
pytest tests/unit/test_http_client.py -v
```

---

## Setup & Commands

**Initial Setup:**
```bash
# Install Python dependencies (from wheelhouse, offline)
pip install --no-index --find-links=vendor/wheels -r requirements-test.txt

# Download Llama 3.3 8B model
chmod +x download_model.sh
./download_model.sh

# Initialize and start all services
chmod +x init.sh
./init.sh
```

**Build:** 
```bash
docker compose build
make build
```

**Tests:** 
```bash
# Unit tests (offline)
pytest tests/unit/ -v

# With Make
make test-unit
```

**Dev Server:** 
```bash
docker compose up -d
make start
```

## File Structure

```
.
├── vendor/
│   └── wheels/              # Offline Python wheels (committed to git)
├── requirements-test.txt    # Test dependencies (pip downloads these to vendor/wheels)
├── tests/
│   ├── unit/
│   └── integration/
├── Dockerfile.api
├── docker-compose.yml
└── api_server.py
```

## Key Rules (CONTRATS.md)

- **Codex environment**: offline only, no network, no Docker local
- **Depen dencies**: wheelhouse source of truth (`vendor/wheels/`)
- **Tests**: unit (Codex) + integration (CI cloud)
- **Signals**: network failures in Codex = bruit (expected)

Read **CONTRATS.md** for full architectural rules.

---

*Updated: Codex dependency management workflow documented*
