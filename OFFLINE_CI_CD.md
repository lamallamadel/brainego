# Offline CI/CD Setup - No Egress Policy

## Problem

GitHub Actions runner has **proxy/egress policy blocking external pip downloads (403)**.
Any `pip install <package>` from PyPI during CI fails.

## Solution: Offline Wheelhouse

All test dependencies are **pre-downloaded and vendoried** in `vendor/wheels/`.

### How it works

1. **One-time setup** (on machine with Internet):
   ```bash
   bash scripts/generate-wheelhouse.sh
   # Downloads all wheels to vendor/wheels/
   ```

2. **CI/CD uses offline install**:
   ```bash
   pip install --no-index --find-links=vendor/wheels -r requirements-test.txt
   # Zero network access, zero proxy issues
   ```

3. **Commit and push**:
   ```bash
   git add vendor/wheels/
   git commit -m "Add offline wheels for CI/CD"
   git push
   ```

### Files

| File | Purpose |
|------|---------|
| `requirements-test.txt` | Minimal test deps (no heavy ML libs) |
| `vendor/wheels/` | Pre-downloaded .whl files |
| `scripts/generate-wheelhouse.sh` | Script to generate wheels |
| `.github/workflows/codex-build.yml` | Uses `--no-index --find-links` |

### Test Dependencies Included

- pytest, pytest-asyncio, pytest-cov
- testcontainers (for integration tests)
- fastapi, pydantic, httpx (core API)
- redis, neo4j, qdrant-client, psycopg2 (for mocking services)
- pyyaml (for config)

### Regenerate Wheelhouse

When you update `requirements-test.txt`:

```bash
# On a machine WITH Internet:
python -m pip install pip-tools  # if needed
bash scripts/generate-wheelhouse.sh

# Then commit:
git add vendor/wheels/
git commit -m "Update offline wheels for new dependencies"
git push
```

### CI/CD Workflow

The GitHub Actions workflow (`.github/workflows/codex-build.yml`) now uses:

```yaml
- name: Install test dependencies (offline)
  run: |
    python -m pip install --upgrade pip
    python -m pip install --no-index --find-links=vendor/wheels -q -r requirements-test.txt
```

✅ **No egress**, ✅ **No 403 errors**, ✅ **Reproducible**

### What if you need a new test dependency?

1. Add it to `requirements-test.txt`
2. Run `bash scripts/generate-wheelhouse.sh` on a machine with Internet
3. Commit `vendor/wheels/` to the repo
4. Done - CI will pick it up automatically

### Benefits

| Benefit | Impact |
|---------|--------|
| Zero network in CI | ✅ Works behind any proxy |
| Reproducible builds | ✅ Same wheels every time |
| Fast | ✅ Local filesystem, no download |
| Offline-friendly | ✅ Works in airgapped networks |
| Simple | ✅ Just `--no-index --find-links` |

### Troubleshooting

**"ModuleNotFoundError: No module named 'pytest'"**
→ Wheels not in `vendor/wheels/` or path is wrong
→ Run `bash scripts/generate-wheelhouse.sh` and recommit

**"ERROR: Could not find a version that satisfies the requirement..."**
→ Dependency missing from wheelhouse
→ Update `requirements-test.txt`, regenerate, recommit

**"pip: command not found"**
→ Python not in PATH
→ Use full path: `/usr/bin/python3 -m pip`
