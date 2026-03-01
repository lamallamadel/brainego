# AGENTS.md - Rules & Workflows

⚠️ **CRITICAL: Read CONTRATS.md first**

This file defines how agents (Codex, humans, CI) interact with brainego.

👉 **The law of brainego is in CONTRATS.md** - all invariants, responsibilities, and non-negotiable rules.

This AGENTS.md is the operational reference for setup, commands, and style.

---

## Linear Batch Tasks & PR Workflow (INST-01)

### Git workflow

* Work on a single feature branch unless told otherwise.
* Process requested Linear issues strictly in the order provided.
* Do not start the next issue before:
  1. code changes are complete,
  2. relevant tests pass,
  3. one git commit is created for the current issue.

### Commit rules

* Exactly one commit per Linear issue.
* Commit message format:

  `<type>(<issue>): <summary>`
* Example:

  `feat(AFR-XYW): add campaign metadata validator`

### Pull request rules

* Open exactly one PR after all requested issues are complete.
* PR title format:

  `batch(linear): AFR-XYA AFR-XYB AFR-XYC AFR-XYD`
* PR body must contain one section per issue with:
  * what changed
  * tests run
  * risk / notes

### Stop conditions

* If one issue is blocked, stop immediately and report the blocker.
* Never silently skip an issue.

---

## Codex Resource Unavailability Pattern (Formal & General)

**Problem:** Codex Cloud is completely offline (zero network, zero shell access for pip/docker/etc).
Codex may generate code that requires resources (Python packages, external files, services) that cannot be satisfied locally.

**Solution:** Formal **resource unavailability protocol** (not specific to dependencies, but generalizable).

### Protocol: When Codex Encounters Resource X Not Available

**Codex's Responsibility:**

1. **Declare resource need explicitly** (in code comments):
   ```python
   # Needs: <resource_type>:<resource_spec>
   # Needs: python-package:httpx>=0.25.1
   # Needs: python-package:fastapi>=0.104.1
   # Needs: file:config/agent-router.yaml
   # Needs: service:qdrant (optional, for integration tests)
   ```

2. **Do NOT attempt to satisfy the resource** (impossible offline)
   - ❌ `pip install package` (no pip in Codex Cloud)
   - ❌ `docker pull image` (no Docker in Codex Cloud)
   - ❌ `curl https://...` (no network in Codex Cloud)
   - ❌ Create/modify `vendor/wheels/` (opérateur only)

3. **Generate code/tests assuming resource IS available** (defer validation)
   ```python
   # This file assumes httpx is installed (by operator before running)
   import httpx  # Will fail if httpx not in wheelhouse, but that's ok
   
   async def test_http_client():
       async with httpx.AsyncClient() as client:
           # test code
   ```

4. **Commit the code** (with `# Needs:` declarations)
   - Git commit → operator sees the declarations
   - Operator can now act

**Operator's Responsibility:**

When operator sees `# Needs: python-package:X`:

```bash
# 1. Verify the need is reasonable
# 2. Add to requirements-test.txt or appropriate file
# 3. Satisfy the resource (download wheels, create files, etc.)
# 4. Commit and push
# 5. Codex can now proceed (on next run)
```

Example for python-package:
```bash
# Add to requirements-test.txt
echo "httpx>=0.25.1" >> requirements-test.txt

# Download wheels (machine with internet)
python -m pip download -d vendor/wheels httpx

# Commit
git add vendor/wheels/ requirements-test.txt
git commit -m "Add httpx wheels (requested by Codex for AFR-27)"
git push
```

### Resource Types (Not Exhaustive, Extensible)

| Resource Type | Example | Codex Action | Operator Action |
|---------------|---------|--------------|-----------------|
| `python-package` | `httpx>=0.25.1` | Declare in `# Needs:` | Add to requirements, download wheel |
| `file` | `config/agent-router.yaml` | Declare in `# Needs:` | Create/provide file, commit |
| `service` | `qdrant` (for integration tests) | Declare in `# Needs:` | Available only in CI Docker, not Codex |
| `data` | `models/llama-3.3-8b.gguf` | Declare in `# Needs:` | Download/store, update .gitignore |
| `tool` | `docker` (for build) | Declare in `# Needs:` | Available in CI, not Codex |

### Formal State Machine: Codex + Operator Loop

```
┌─────────────────────────────────────────────────────────────┐
│ Codex generates code that depends on Resource X             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │ Codex can satisfy X?  │
         └───┬─────────────┬─────┘
             │ YES         │ NO
             │             │
             ▼             ▼
        [Use X]     ┌─────────────────────┐
        [Test]      │ Declare # Needs: X  │
        [Done]      │ Generate code       │
                    │ (assume X present)  │
                    │ Commit              │
                    └──────────┬──────────┘
                               │
                               ▼ (operator sees commit)
                    ┌─────────────────────────────────┐
                    │ Operator: Is X request valid?   │
                    └───┬─────────────┬───────────────┘
                        │ YES         │ NO
                        │             │
                        ▼             ▼
                   [Satisfy X]    [Reject + explain]
                   [Commit]       [Codex adjusts code]
                   [Push]         [Loop]
                        │
                        ▼
                   ┌──────────────────────┐
                   │ Next Codex run:      │
                   │ X now available      │
                   │ Tests pass           │
                   │ Done                 │
                   └──────────────────────┘
```

### Examples

**Example 1: Missing Python Package**

Codex generates:
```python
# tests/unit/test_lightweight_api.py
# Needs: python-package:fastapi>=0.104.1
# Needs: python-package:pydantic>=2.5.0

import fastapi
from pydantic import BaseModel

class ChatRequest(BaseModel):
    messages: list

@fastapi.get("/v1/chat")
async def chat(req: ChatRequest):
    return {"response": "..."}
```

Codex tries to test → **ModuleNotFoundError: No module named 'fastapi'** (expected in Codex Cloud).

Codex action: ✅ Stop. Commit anyway (has `# Needs:` declarations).

Operator action:
```bash
# See # Needs: declarations in code
# Add to requirements-test.txt
echo "fastapi>=0.104.1" >> requirements-test.txt
echo "pydantic>=2.5.0" >> requirements-test.txt

# Download wheels
python -m pip download -d vendor/wheels fastapi pydantic

# Commit
git add vendor/wheels/ requirements-test.txt
git commit -m "Add fastapi, pydantic wheels (needed by AFR-27 API tests)"
git push
```

**Example 2: Missing Config File**

Codex generates:
```python
# src/agent_router.py
# Needs: file:configs/agent-router.yaml

import yaml

with open("configs/agent-router.yaml") as f:
    config = yaml.safe_load(f)
```

Codex tries to load → **FileNotFoundError: configs/agent-router.yaml** (expected).

Codex action: ✅ Stop. Declare in `# Needs:`. Commit.

Operator action:
```bash
# Create the file (or provide it)
mkdir -p configs
cat > configs/agent-router.yaml << 'EOF'
agents:
  - name: main
    model: llama-3.3-8b
EOF

# Commit
git add configs/agent-router.yaml
git commit -m "Add agent-router.yaml (requested by agent_router.py)"
git push
```

**Example 3: Integration Test Needs Service (Qdrant)**

Codex generates:
```python
# tests/integration/test_rag_query.py
# Needs: service:qdrant (for integration tests only)

import qdrant_client

def test_qdrant_query():
    client = qdrant_client.QdrantClient(host="qdrant", port=6333)
    # ... test code
```

Codex action: ✅ Declare service need. Mark test as `@pytest.mark.integration`. Commit.

Operator/CI action:
```bash
# This test is marked integration, CI will run it in Docker
# where qdrant service is available (docker-compose.yml)
pytest tests/integration/ -v  # CI only, not Codex
```

---

## Codex Environment Constraints (Hard Boundaries)

**Codex Cloud = Completely Offline**

| Capability | Available? | Notes |
|------------|-----------|-------|
| Python code generation | ✅ Yes | Core function |
| `python -m py_compile` | ✅ Yes | Syntax check only |
| `pytest tests/unit/` | ⚠️ Conditional | Only if all `# Needs:` satisfied |
| `pip install` | ❌ No | Zero network, zero shell |
| `docker` commands | ❌ No | No Docker daemon |
| `curl / requests` HTTP | ❌ No | No network egress |
| File I/O (read/write) | ✅ Yes | Local filesystem only |
| Git operations | ✅ Yes | Via platform (create branch, commit, PR) |
| External service access | ❌ No | Qdrant, Redis, etc. not available |

**Consequence:** If code depends on unavailable resource, Codex:
1. Declares it (`# Needs:`)
2. Generates code assuming it's available
3. Commits (operator handles satisfaction)

---

## Unit Tests in Codex (When Dependencies Available)

**Prerequisites:**
1. All `# Needs: python-package:...` already satisfied (wheels in vendor/wheels/)
2. Operator has run: `python -m pip install --no-index --find-links=vendor/wheels -r requirements-test.txt`

**Then Codex can:**
```bash
# Syntax check
python -m py_compile <file>.py

# Run unit tests (offline, no external services)
pytest tests/unit/ -v
```

**Unit test definition:** Test that requires zero external services (no Docker, no network, no Qdrant/Redis/etc).

---

## Setup & Commands (For Operator/CI)

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

**Tests (Unit - Codex compatible):** 
```bash
# Unit tests (offline, no services)
pytest tests/unit/ -v

# With Make
make test-unit
```

**Tests (Integration - CI only):**
```bash
# Integration tests (requires services, CI Docker only)
pytest tests/integration/ -v

# With Make
make test-integration
```

**Dev Server:** 
```bash
docker compose up -d
make start
```

---

## File Structure

```
.
├── vendor/
│   └── wheels/              # Offline Python wheels (committed to git)
├── requirements-test.txt    # Test dependencies (pip downloads these to vendor/wheels)
├── tests/
│   ├── unit/                # Codex + operator (offline tests)
│   ├── integration/         # CI only (requires services)
│   └── contract/            # Codex + operator (offline tests)
├── configs/
│   └── agent-router.yaml    # Operator provides
├── Dockerfile.api
├── docker-compose.yml
└── src/
    ├── api_server.py
    ├── rag_service.py
    └── memory_service.py
```

---

## Key Rules (CONTRATS.md)

- **Codex environment**: offline only, no network, no Docker, no pip, no shell
- **Resource unavailability**: Declare with `# Needs:`, do NOT attempt to satisfy
- **Dependencies**: wheelhouse (`vendor/wheels/`) is source of truth
- **Tests**: unit/contract (Codex) + integration/e2e (CI only)
- **Signals**: resource not found in Codex = bruit (expected, not error)

Read **CONTRATS.md** for full architectural rules.

---

*Updated: Codex Resource Unavailability Pattern (formal, general, not specific to packages)*
