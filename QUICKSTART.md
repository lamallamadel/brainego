# Quick Start: Docker Build Cloud + Testcontainers Cloud for brainego

## ⚡ Setup (5 minutes)

### Step 1: Get Testcontainers Cloud Token (2 min)

1. Visit: https://cloud.testcontainers.com/
2. Sign in or create account
3. Go to **Settings → API Tokens**
4. Create a new token
5. Copy the token

### Step 2: Add GitHub Secret (2 min)

1. Go to your GitHub repo: `Settings → Secrets and variables → Actions`
2. Click **New repository secret**
3. Name: `TESTCONTAINERS_CLOUD_TOKEN`
4. Value: Paste the token from Step 1
5. Click **Add secret**

### Step 3: Verify Workflow File (1 min)

Check that `.github/workflows/codex-build.yml` exists in your repo:

```bash
ls -la .github/workflows/
# Should show: codex-build.yml
```

---

## ✅ Verification (2 minutes)

### Test the Pipeline

```bash
# Create a test branch
git checkout -b feature/codex/verify

# Make a small change
echo "# Test" >> README.md

# Commit and push
git add .
git commit -m "Test build pipeline"
git push origin feature/codex/verify
```

### Watch GitHub Actions

1. Go to your repo on GitHub
2. Click **Actions** tab
3. Find "Codex Feature Build & Test" workflow
4. Click on the run
5. Wait 5-10 minutes for results

**Expected result**:
```
✅ build-and-test (passed)
   ├── Build API image
   ├── Build gateway image
   ├── Build MCPJungle image
   ├── Run unit tests
   └── Run integration tests

✅ security-scan (passed)
   └── Trivy scan completed

✅ notify (passed)
```

---

## 📋 Checklist for Codex

When Codex generates code on `feature/codex/*` branches:

- [ ] Create unit tests in `tests/unit/`
- [ ] Create integration tests in `tests/integration/` (if using services)
- [ ] Use **Testcontainers** for Redis, PostgreSQL, etc.
- [ ] Update `requirements.txt` if adding dependencies
- [ ] Follow patterns in `CODEX_INSTRUCTIONS.md`
- [ ] Push to `feature/codex/*` (NOT main!)

---

## 🔍 What Happens Automatically

### When Codex Pushes Code

```
feature/codex/new-feature branch
    ↓
GitHub detects branch pattern
    ↓
Workflow "codex-build.yml" triggers
    ├─ Build images via Docker Build Cloud ☁️
    ├─ Push to GitHub Container Registry 📦
    ├─ Run unit tests 🧪
    ├─ Run integration tests with Testcontainers Cloud ☁️
    ├─ Security scan 🛡️
    └─ Post results to PR 📝
    ↓
Feedback in PR (5-10 minutes)
```

### No Docker on Codex Cloud ✅

Codex doesn't need Docker. The workflow:
- ✅ Builds via **Docker Build Cloud** (remote buildx)
- ✅ Tests via **Testcontainers Cloud** (cloud Docker daemon)

---

## 📂 Files Created

| File | Purpose |
|------|---------|
| `.github/workflows/codex-build.yml` | CI/CD pipeline (GitHub Actions) |
| `CODEX_INSTRUCTIONS.md` | Instructions for Codex |
| `GITHUB_ACTIONS_SETUP.md` | Detailed setup guide |
| `CI_CD_SUMMARY.md` | This entire CI/CD system |
| `tests/conftest.py` | Pytest config & fixtures |
| `tests/unit/test_api_endpoints.py` | Unit test examples |
| `tests/integration/test_services.py` | Integration test examples |
| `pytest.ini` | Pytest configuration |

---

## 🚀 Next Steps

### Immediate

1. ✅ Add `TESTCONTAINERS_CLOUD_TOKEN` secret (Step 1-2 above)
2. ✅ Test with dummy branch (Verification above)
3. ✅ Share `CODEX_INSTRUCTIONS.md` with Codex

### This Week

- [ ] Have Codex generate a small feature (with tests)
- [ ] Verify workflow passes
- [ ] Merge to main

### Optional Enhancements

- [ ] Enable multi-arch builds (ARM64 + AMD64)
- [ ] Add Slack notifications
- [ ] Add code coverage reports
- [ ] Performance benchmarks

---

## 🐛 Troubleshooting

### "Workflow not found"
**Fix**: Push to a `feature/codex/*` branch (not other branches)

### "Testcontainers Cloud timeout"
**Fix**: Increase timeout in `.github/workflows/codex-build.yml`:
```yaml
env:
  TESTCONTAINERS_TIMEOUT: 120
```

### "Can't find secret"
**Fix**: Go to `Settings → Secrets and variables` and verify `TESTCONTAINERS_CLOUD_TOKEN` exists

### "Docker build rate limited"
**Fix**: Use specific image versions:
```dockerfile
FROM python:3.11.8-slim  # ✅ Specific version
# FROM python:3.11-slim  # ❌ Can rate limit
```

---

## 📊 Your Setup

### Docker Build Cloud Status
```bash
docker buildx ls

# Current output:
NAME/NODE           DRIVER/ENDPOINT     STATUS    BUILDKIT
default             docker              running   v0.27.0
desktop-linux*      docker              running   v0.27.0
```

Both builders support `linux/amd64 (+4)` platforms.

### Testcontainers Cloud Status
- Token: Stored as GitHub Secret
- Status: Ready to use in GitHub Actions
- Auto-detects cloud environments

---

## 📚 Documentation

| Document | For | Link |
|----------|-----|------|
| `CODEX_INSTRUCTIONS.md` | Codex | How to generate code + tests |
| `GITHUB_ACTIONS_SETUP.md` | Setup | Detailed configuration |
| `CI_CD_SUMMARY.md` | Reference | Complete system overview |
| Docker Build Cloud | Docs | https://docs.docker.com/build-cloud/ |
| Testcontainers Cloud | Docs | https://testcontainers.com/cloud/docs/ |

---

## ✨ Summary

You now have:

✅ **Docker Build Cloud** - Builds images in the cloud  
✅ **Testcontainers Cloud** - Tests with real services  
✅ **GitHub Actions** - Automated CI/CD pipeline  
✅ **Example Tests** - Unit + integration test patterns  
✅ **Codex Ready** - Instructions for Codex to follow  

**All set! Codex can start generating features on `feature/codex/*` branches.** 🚀

---

## Questions?

1. **"Can I use this locally?"** → Yes! Install testcontainers and use the same tests locally
2. **"Multi-arch builds?"** → Yes, add `platforms: linux/amd64,linux/arm64` to workflow
3. **"Cost of cloud builds?"** → Depends on your Docker Build Cloud plan; see dashboard
4. **"Test feedback time?"** → Usually 5-10 minutes; depends on test complexity

Need help? See the full documentation files:
- `GITHUB_ACTIONS_SETUP.md` - Technical details
- `CODEX_INSTRUCTIONS.md` - Code generation patterns
