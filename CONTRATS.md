# Contrats Fondamentaux de brainego

Ce document définie la loi non-négociable qui gouverne brainego: architecture, tests, dépendances, et comportement des agents (Codex inclus).

---

## 1. Séparation des Environnements

### 1.1 Environnement Codex (Agent Stage)

**Autorisé:**
- `python -m py_compile` (vérification syntaxe)
- Tests unitaires (tests/unit/)
- Validations offline uniquement
- Génération de code, documentation, refactoring

**Interdit:**
- Docker
- Appels HTTP externes (curl, urllib, requests vers sites externes)
- `pip install` sans `--no-index --find-links=vendor/wheels`
- Tout accès réseau externe

**Règle:**
Codex = validation offline + génération de code
Codex ≠ intégration, infrastructure, déploiement

### 1.2 Environnement CI Docker Cloud

**Responsabilité:**
- Builds Docker via Docker Build Cloud
- Tests d'intégration (API + MAX, RAG + Qdrant, Memory + API, etc.)
- Tests end-to-end
- Tests de performance
- Sécurité + observabilité

**Services disponibles:**
- MAX Serve
- Qdrant
- Redis
- PostgreSQL
- Neo4j
- Testcontainers Cloud

### 1.3 Environnement Production (Kubernetes)

**Responsabilité:**
- Déploiement multi-node
- Observabilité complète (Grafana, Jaeger, Prometheus)
- SLO / monitoring / alertes
- Disaster recovery, backups
- Policy réseau stricte

---

## 2. Contrat des Dépendances (I1 - Dépendances Offline)

### 2.1 Règle d'Or

```
Toute dépendance Python requise par un test ou script
doit être disponible via une source offline approuvée.

Aucun pip install en ligne n'est autorisé dans:
  - Codex
  - CI/CD jobs
  - Environnements de validation
```

### 2.2 Source Unique de Vérité

Les dépendances Python existent **uniquement** via:
1. **vendor/wheels/** (wheelhouse offline pour tests)
2. **Image CI prébuildée** (pour services + runtime)

### 2.3 Processus d'Ajout de Dépendance

Quand une nouvelle dépendance est nécessaire:

1. **Agent/Codex demande explicitement** (commentaire `# Needs: package>=version`)
2. **Opérateur ajoute à requirements-test.txt ou requirements-dev.txt**
3. **Opérateur génère les wheels** (une seule fois, machine avec Internet):
   ```bash
   python -m pip download -d vendor/wheels package>=version
   ```
4. **Commit vendor/wheels/** au repo
5. **Codex/Agent peut maintenant utiliser la dépendance**

**Jamais:**
- Codex n'exécute `pip install`
- Codex ne télécharge de packages
- Codex ne modifie le wheelhouse

### 2.4 Installation Offline en CI/Test

Toute installation Python dans un job doit être:

```bash
python -m pip install --no-index --find-links=vendor/wheels -r requirements-test.txt
```

Jamais:
```bash
pip install package  # ❌
pip install -r requirements.txt  # ❌ (si connexion en ligne)
```

---

## 3. Classification Stricte des Tests (I2 - Environnement)

### 3.1 Taxonomie Officielle

| Type | Location | Env | Services | Codex? | Responsable |
|------|----------|-----|----------|--------|-------------|
| **unit** | tests/unit/ | Offline | Aucun | ✅ | Dev + Codex |
| **contract** | tests/contract/ | Offline | Doublures locales | ✅ | Dev + Codex |
| **integration** | tests/integration/ | CI Docker | Vrais containers | ❌ | Dev + Codex (génère), CI (exécute) |
| **e2e** | tests/e2e/ | CI Docker | Full stack | ❌ | Dev |
| **perf** | tests/perf/ | CI spécial | Staging | ❌ | DevOps + Dev |

### 3.2 Définitions

**Unit Tests**
- Testent une fonction ou classe isolée
- Zéro dépendance externe
- Zéro Docker, zéro réseau
- < 1 seconde généralement

**Contract Tests**
- Testent les contrats d'API (schemas, statuts HTTP, formats)
- Peuvent utiliser des doublures/mocks
- Validation de structure, pas logique métier
- < 2 secondes généralement

**Integration Tests**
- Testent plusieurs composants ensemble
- Nécessitent services réels (MAX, Qdrant, Redis, etc.)
- Via Testcontainers Cloud
- 5-60 secondes

**E2E Tests**
- Flots complets: chat → mémoire → RAG → réponse
- Maximum d'isolation + réalisme
- Lents mais complets
- CI/staging uniquement

**Perf Tests**
- Latence, throughput, charge
- Nécessitent baseline stable
- Staging ou CI spécial

### 3.3 Règle d'Exécution

```
test lancé => environnement ∈ domaines_autorisés(test)

Un test lancé hors de son domaine nominal
= signal invalide / bruit
= ne peut pas invalider le produit
```

---

## 4. Signal vs Bruit (I3 - Signaux Valides)

### 4.1 Signaux Valides (Production Verdict)

✅ Compilation réussie (`python -m py_compile`)
✅ Tests unitaires réussis dans Codex
✅ Tests d'intégration réussis dans CI Docker
✅ Couverture de code sur composants critiques
✅ Métriques / logs / traces attendues émises
✅ Validations de contrat API réussies

### 4.2 Signaux Invalides (Bruit - Ignoré)

❌ `curl / urllib` vers sites externes dans tests
❌ Absence de Docker dans Codex (c'est prévu)
❌ Erreurs `pip install` online (proxy 403, egress bloqué)
❌ Tests lancés dans mauvais environnement
❌ Dépendances non disponibles offline (avant d'être ajoutées au wheelhouse)
❌ Web lookups (documentation, Wikipedia, moteurs de recherche)
❌ DNS external résolvé dans tests

### 4.3 Traduction Concrète

| Événement | Interprétation | Action |
|-----------|---|---|
| pip install 403 dans Codex | Bruit (egress bloqué) | Ignorer. Ajouter à wheelhouse. |
| Integration test fails localement | Bruit (pas censé tourner localement) | C'est normal. Doit tourner en CI. |
| pytest-asyncio pas installé | Bruit → faille de wheelhouse | Vérifier vendor/wheels/. Ajouter wheels. |
| httpx importé mais pas en wheelhouse | Faille clairement identifiable | Ajouter httpx à vendor/wheels/. |
| curl wikipedia dans test | Bruit → test mal classé | Retirer l'appel. Utiliser mock. |

---

## 5. Évolution d'Architecture (I4 - Évolution)

### 5.1 Architecture de Référence

brainego repose sur:

```
MAX Serve (inference)
  ├─ Llama 3.3 8B (base model)
  ├─ LoRA adapters (fine-tuning)
  └─ EWC / Elastic Weight Consolidation (continual learning)

+ RAG Pipeline
  ├─ Qdrant (vector DB)
  ├─ Neo4j (graph knowledge)
  ├─ Redis (cache)
  └─ Chunking + retrieval

+ Memory System (Mem0)
  ├─ Fact extraction
  ├─ Scoring (temporal decay, similarity)
  └─ Consolidated context

+ MCP Integration (MCPJungle)
  ├─ Tool access
  ├─ Multi-provider support
  └─ Gateway routing

+ Infrastructure
  ├─ Kubernetes (self-hosted)
  ├─ PostgreSQL (feedback, audit)
  ├─ Observability (Prometheus, Grafana, Jaeger)
  └─ Security (RBAC, TLS, Kong API Gateway)
```

### 5.2 Règle d'Évolution

```
nouvelle_fonctionnalité:

  SI compatible(architecture_référence):
    ✅ Acceptée directement
  
  SINON:
    Nécessite:
      1. Issue / ADR (Architecture Decision Record)
      2. Validation de compatibilité ou changement d'archi
      3. PR avec tests
```

### 5.3 Exemples

✅ Ajouter un nouvel endpoint /v1/rag/search → compatible, procédez
✅ Utiliser Faiss au lieu de Qdrant → non-compatible, créer ADR
❌ Introduire LangChain comme orchestrateur → non-compatible sans décision
❌ Changer MAX pour vLLM → changement fondamental, nécessite ADR

---

## 6. Invariant d'Observabilité (I5 - Non-Régression)

### 6.1 Règle

Tout changement sensible doit maintenir ou améliorer l'observabilité:

```
changement_sensible => observabilité_nouvelle >= observabilité_précédente
```

### 6.2 Composants Sensibles

- Scoring mémoire (decay, similarité)
- Routing d'agents (intent classification, model selection)
- Drift detection (KL divergence, PSI)
- Fine-tuning / LoRA training
- Gateway MCP (tool execution, fallback chain)
- Circuit breakers (state transitions)

### 6.3 Observabilité Minimale

Chaque composant sensible doit exposer:

| Métrique | Type | Exemple |
|----------|------|---------|
| Débit | Counter | `memory_lookups_total` |
| Latence | Histogram | `memory_lookup_latency_ms` |
| Erreurs | Counter | `memory_errors_total` |
| État | Gauge | `circuit_breaker_state` |
| Logs structurés | Logs | `{"component":"memory","action":"decay","user":"...",...}` |
| Traces (Jaeger) | Traces | Chaîne complète: intent → model → RAG → mémoire → réponse |

### 6.4 Vérification

Avant de committer un changement sur composant sensible:

```bash
# Vérifier que les métriques / logs existent
grep -r "memory_score" . --include="*.py"
grep -r "drift_detected" . --include="*.py"

# Vérifier que les dashboards sont à jour
# (Grafana: Drift Overview, Memory Scoring, etc.)
```

---

## 7. Contrat des Agents (Codex Inclus)

### 7.1 Statut des Agents

Agents = **outils** dans brainego
Agents ≠ **législateurs**

Codex / autres agents:
- ✅ Respectent cette loi
- ✅ Modifient du code / tests / docs dans les domaines autorisés
- ✅ Demandent explicitement les dépendances manquantes
- ❌ Ne définissent pas de nouveaux contrats
- ❌ Ne contournent pas les restrictions

### 7.2 Droit des Agents

Codex peut:
- Générer / modifier code dans tests/unit/, tests/contract/, src/
- Ajouter / mettre à jour tests unitaires
- Écrire / mettre à jour documentation
- Refactoriser du code existant
- Ajouter des commentaires / docstrings

Codex ne peut pas:
- Modifier .github/workflows/ (CI/CD) sans issue + PR humaine
- Ajouter dépendances sans demander explicitement
- Installer packages online
- Changer l'architecture (services, endpoints publics)
- Ouvrir l'accès réseau dans Codex
- Créer de nouveaux contrats / politiques

### 7.3 Protocol de Demande (Générique - Resource Unavailability)

Voir Section 8 (Invariant I7).

### 7.4 Clause de Refus

Si Codex ne peut pas satisfaire une consigne sans violer cette loi:

```
Réponse correcte:
"Je ne peux pas le faire sans violer la loi fondamentale de brainego.
Spécifiquement: [I1|I2|I3|I4|I5|I6|I7]

Pour procéder, il faut [ajouter au wheelhouse | créer ADR | accepter bruit | déclarer # Needs: | ...]"
```

Pas de bricolage autour.

---

## 8. Invariant de Ressource (I7 - Resource Unavailability Pattern)

### 8.1 Contexte

Codex Cloud est **complètement offline** (zéro réseau, zéro pip, zéro docker, zéro shell).
Codex peut générer du code qui dépend de ressources indisponibles localement:
- Packages Python (fastapi, qdrant-client, etc.)
- Fichiers de config (configs/agent-router.yaml)
- Services externes (Qdrant, Redis, MAX Serve)
- Outils (docker, kubectl)

### 8.2 Invariant I7 (Formel & Général)

```
code_généré_dépend_de_ressource_X:

  SI Codex peut satisfaire X localement:
    ✅ Satisfait X
    ✅ Teste le code
    ✅ Commit final

  SINON (X indisponible en Codex):
    ✅ Déclare X explicitement (# Needs: <type>:<spec>)
    ✅ Génère code (assume X disponible)
    ✅ Commit (opérateur verra # Needs:)
    ❌ NE PAS tenter de satisfaire X
    ❌ NE PAS bricoler autour
```

### 8.3 Ressources Couvertes (Extensible)

| Type | Exemple | Codex Action | Operator Action |
|------|---------|--------------|-------------|
| `python-package` | `fastapi>=0.104.1` | Déclare `# Needs:` | Ajoute à wheelhouse, download, commit |
| `file` | `configs/agent-router.yaml` | Déclare `# Needs:` | Crée/fourni file, commit |
| `service` | `qdrant` | Déclare `# Needs:` (mark test @integration) | CI Docker fournit le service |
| `tool` | `docker` | Déclare `# Needs:` | Disponible en CI, pas Codex |
| `data` | `models/llama-3.3-8b.gguf` | Déclare `# Needs:` | Download/store, update .gitignore |

### 8.4 Violation I7

❌ Codex tente `pip install package` → interdit (zéro pip)
❌ Codex tente `docker pull image` → interdit (zéro docker)
❌ Codex tente `curl https://...` → interdit (zéro réseau)
❌ Codex génère code sans déclarer `# Needs: X` → ressource manquante non documentée
❌ Codex bricode autour (try/except pour contourner absence) → masque le problème

### 8.5 Bénéfice

```
Avant (chaos):
  Codex: "pip install fastapi failed"
  → Erreur incompréhensible, frustration

Après (I7 clear pattern):
  Codex: "FastAPI pas dispo, déclare # Needs:, continue"
  Operator: "Voit # Needs:, ajoute fastapi au wheelhouse"
  → Workflow clair, reproductible, pas de boucle infernale
```

---

## 9. Garantie Observable des Agents (Codex + Autres)

### 9.1 Le Problème

Les agents peuvent réciter les règles sans les appliquer (boucle infernale):
- Soit faire sans cadre (ignorance des règles)
- Soit lire le cadre sans faire (performativité creuse)

**Solution:** Contrat d'**auditabilité non-ambigüe** à chaque sortie d'agent (I6).

### 9.2 État de Sortie (Falsifiable)

Tout agent doit finir dans UN seul état valide:

```
État V1: Zéro modification code
  → pas de commit
  → pas de PR
  → raison technique explicite
  → exemple: "pas de modif nécessaire" ou "erreur bloquante: [..]"

État V2: Changements code validés
  → tests/checks exécutés
  → git commit fait
  → PR générée ou raison explicite pourquoi non
  → exemple: "3 fichiers modifiés, 4 tests passants, PR#123"

Tout autre état = erreur détectable immédiatement
```

### 9.3 Preuves Obligatoires (Pas de "Crois-Moi")

Avant de déclarer "terminé", agent fournit:

```bash
# 1. État du repo
git status --short
git log -1 --oneline

# 2. Fichiers touchés
ls -la <fichiers modifiés>

# 3. Checks exécutés (offline conformes)
python -m py_compile $(find . -name '*.py')
pytest tests/unit/ -v --tb=short
python validate_wheels.py

# 4. Résultat de chaque check
# [✅] Check 1: ...
# [✅] Check 2: ...
# [❌] Check 3: raison pourquoi acceptable ou non
```

### 9.4 Gate de Vérification (Avant "Terminé") - I6

Agent doit cocher ces cases:

```
[INVARIANTS VÉRIFIÉS AVANT CONCLUSION]

☐ Règles lues: AGENTS.md + CONTRATS.md consultés
☐ Scope clair: Tâche X = Y résultat attendu
☐ Ressources: I7 checklist (# Needs: déclarés si nécessaire)
☐ Dépendances: Offline uniquement, validate_wheels.py ok
☐ Tests offline: py_compile + pytest unit réussis (ou skipped avec raison)
☐ Zéro web lookup: Aucun curl/requests/urllib extern
☐ Commit cohérent: État final = V1 ou V2 (jamais état mixte)
☐ Preuves jointes: git status + checks logs + fichiers

Si UN point manque: NE PAS conclure "terminé"
Conclure plutôt: "bloqué sur [X], raison: [Y], prochaine action: [Z]"
```

### 9.5 Exemple: Sortie Conforme vs Non-Conforme

**❌ Non-Conforme (Boucle Infernale)**
```
"J'ai relu AGENTS.md et CONTRATS.md.
Codex doit rester offline.
J'ai exécuté py_compile.
Conclusion: Tâche conforme."

❌ Problèmes:
  - Zéro fichier créé/modifié listé
  - Zéro git status fourni
  - Zéro lien vers fichiers modifiés
  - Déclaration sans preuve
```

**✅ Conforme (Auditabilité + I7)**
```
[INVARIANTS VÉRIFIÉS]
☑ Scope: Impl API /v1/chat + /v1/rag/query + tests
☑ I7: Tests marqués @unit (pas de services), # Needs: python-package:fastapi déclaré
☑ Offline: fastapi, pytest en wheelhouse ✅
☑ Tests: py_compile ✅, pytest tests/unit/ ✅
☑ Code: 3 fichiers modifiés (api_server.py, rag_service.py, test_...py)
☑ Zéro web: Aucun curl, requests, urllib vers internet

Changements:
$ git status --short
 M api_server.py
 M rag_service.py
 A tests/unit/test_unified_chat.py

$ git log -1 --oneline
7a3f8c2 Impl AFR-27: Lightweight API service

Checks exécutés:
$ python -m py_compile api_server.py rag_service.py
✅ Compilation OK

$ pytest tests/unit/test_unified_chat.py -v
✅ 6/6 tests passed

$ python validate_wheels.py
✅ All 14 requirements in wheelhouse

État: V2 (changements validés, prêt PR)
```

### 9.6 Limite Transparente (Pas de Faux Contrat)

Agent reconnaît ses limites:

```
Garantie mathématique absolue (impossible d'échouer): NON
  → Je suis probabiliste, pas preuve formelle

Garantie procédurale vérifiable (traces auditable): OUI
  → git status, logs de tests, commits vérifiables

Conséquence:
  Tu me juges sur observations mesurables, pas intention
  Toute dérive = visible immédiatement via gate
```

---

## 10. Protocol d'Exécution Agent (Appliquable à Tout Agent)

### 10.1 Avant de Commencer

```
1. Lire tâche / issue linéaire
2. Vérifier scope / dépendances
3. Vérifier si compatible avec environnement Codex (I1-I7)
4. Annoncer le plan (jamais faire sans annoncer)
5. Exécuter
6. Vérifier gate [9.4]
7. Si V1 ou V2: conclure
   Sinon: repeller ou refuser explicitement
```

### 10.2 Annonce Obligatoire Avant Première Action

AVANT tout `read_file`, `shell`, `write_file`:

```
"Je vais [action1], puis [action2], puis [action3].
Raisonnement: [Y].
Résultat attendu: [Z].

Contraintes de brainego appliquées:
  - Offline uniquement (✅/❌)
  - Dépendances wheelhouse (✅/❌)
  - Resource Unavailability (I7) (✅/❌)
  - Tests offline (✅/❌)
  - Commit/PR si modif (✅/❌)"
```

### 10.3 Pendant l'Exécution

```
Après chaque étape majeure:
  "Done. Now [prochaine étape]"
  
Jamais:
  "Perfect", "Excellent", "Great" (filler words)
```

### 10.4 À la Fin

```
Fournir tableau:

[INVARIANTS VÉRIFIÉS]
☑/☐ Règles lues
☑/☐ Scope implémenté
☑/☐ I7 checklist (# Needs: si ressources manquantes)
☑/☐ Tests offshore
☑/☐ Commit/PR cohérent
☑/☐ Zéro web lookup

État final: V1 | V2 | BLOQUÉ

Si V1 ou V2:
  git status --short
  git log -1 --oneline
  
Si BLOQUÉ:
  Raison: [...]
  Pré-requis: [...]
  Action suivante: [...]
```

---

## 11. Garde-Fous (Enforcement)

### 11.1 CI/CD Checks

```bash
# Vérifier qu'aucun pip install n'est "online"
grep -R "pip install" .github/workflows/ | grep -v -- "--no-index" && exit 1

# Vérifier que toutes les dépendances testées existent en wheelhouse
pytest --collect-only -q | grep "ImportError" && exit 1

# Vérifier la couverture de composants sensibles
pytest --cov=api_server --cov=memory_service --cov=drift_monitor --cov-report=term-missing

# Vérifier que le wheelhouse est à jour
python validate_wheels.py || exit 1
```

### 11.2 Revue Manuelle

- ✅ Chaque PR doit vérifier: dépendances, classification test, observabilité, I7 declarations
- ✅ Tout changement de CI/architecture/sécurité → humain review obligatoire
- ✅ Chaque sortie agent → vérifier gate [9.4], pas juste "looks good"

---

## 12. Résumé des Invariants

| Invariant | Formule | Violation |
|-----------|---------|-----------|
| **I1** | validation_offline ⟹ deps_offline_disponibles | pip install online en Codex |
| **I2** | test_lancé ⟹ env ∈ domaines_autorisés(test) | integration test dans Codex |
| **I3** | signal ∉ signaux_valides ⟹ signal_invalide | curl wikipedia en test |
| **I4** | nouvelle_brique ⟹ (compatible ∨ ADR_approuvée) | nouveau service sans décision |
| **I5** | changement_sensible ⟹ obs_new ≥ obs_prev | suppression de métriques |
| **I6** | sortie_agent ⟹ État ∈ {V1, V2} | État mixte / déclaration sans preuves |
| **I7** | ressource_indisponible ⟹ Déclare + NE_PAS_satisfaire | Codex tente pip/docker/curl |

---

## 13. Référence Rapide

**Codex generating code?**
→ tests/unit/ + offline uniquement
→ Déclare `# Needs:` si ressource manquante

**Ressource indisponible (fastapi, qdrant, docker)?**
→ Déclare `# Needs: <type>:<spec>` + continue
→ Opérateur satisfait après, commit

**Test échoue à cause de pip 403?**
→ Normal (bruit). I1: ajouter au wheelhouse.

**Test échoue dans Codex mais passe en CI?**
→ Normal. I2: c'est un test integration. Correct.

**Métriques supprimées pour simplifier?**
→ Violation I5. Refuser.

**Nouveau composant ajouté?**
→ Vérifier I4 (compatible + éventuellement ADR)

**Agent sort en boucle (récite sans faire)?**
→ Violation I6. Vérifier gate [9.4].

**Code dépend d'une ressource offline?**
→ I7: Déclarer explicitement `# Needs:`, pas de bricolage.

---

**Statut:** Loi fondamentale v3 (I7: Resource Unavailability Pattern) - À appliquer immédiatement
**Auteur:** Gordon (Docker AI) + Décisions du projet
**Révision:** Annuelle + sur ADR majeure
**Questions:** Créer issue avec tag `[CONTRATS]`
