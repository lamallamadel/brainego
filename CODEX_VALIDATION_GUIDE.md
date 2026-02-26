# Codex Post-Validation Actions

Ce fichier guide Codex après chaque test/validation.

## ✅ Si tout passe

1. Commit automatiquement:
   ```bash
   git add .
   git commit -m "feat: [description of changes]"
   git push origin feature/codex/[branch-name]
   ```

2. Output: ✅ All checks passed. PR ready for review.

## ⚠️ Si le web-search échoue (attendu)

**C'EST OK.** Le web-search n'est pas nécessaire.

Ignore ce message:
```
(web search required by instruction, but blocked in this environment with proxy 403 Forbidden)
```

Raison: Zero egress policy en CI/CD. Aucun réseau externe.

**À faire à la place:**
- ✅ Teste les endpoints localement via `curl http://localhost:PORT/health`
- ✅ Utilise `scripts/max-health-check.sh` pour MAX Serve
- ✅ Utilise Testcontainers Cloud pour les services (pas d'egress, tout en cloud)

## 🔴 Si un test échoue

1. Lis le log d'erreur
2. Corrige le code (ne change pas les tests)
3. Re-run: `pytest -q tests/unit/`
4. Une fois OK, commit et push

## 📝 Test workflow récapitulatif

```
Code generated
  ↓
python -m py_compile [files]  → Syntax check
  ↓ ✅
pytest tests/unit/            → Unit tests
  ↓ ✅
docker compose up (optional)  → Integration (Testcontainers)
  ↓ ✅
git commit + push             → Feature branch
  ↓ (GitHub Actions auto-runs)
CI/CD validates (offline)     → Docker Build Cloud + Testcontainers Cloud
  ↓ ✅
PR ready for merge
```

## ❌ Ne pas faire

- ❌ Web searches (urllib, requests à des sites externes)
- ❌ `pip install` depuis PyPI (zéro réseau)
- ❌ DNS lookups externes
- ❌ HTTP requests à non-localhost

## ✨ Résumé

**Validation locale = Validation CI/CD**

Si ça passe localement (pytest + syntax), ça passera en CI.
