# Contrats Fondamentaux de brainego

Ce document formalise les invariants de base du projet brainego.
Il complète `CONTRATS.md` et sert de référence rapide pour les agents, développeurs et opérateurs.

---

## 1) Séparation des environnements

### 1.1 Codex (agent stage, offline)
- Objectif: produire du code, valider la syntaxe, exécuter des tests offline.
- Autorisé: `python -m py_compile`, tests `unit`/`contract` sans service externe.
- Interdit: Docker, accès réseau externe, installation en ligne de dépendances.
- Règle: un signal issu d'un test hors domaine Codex n'est pas recevable.

### 1.2 CI Docker Cloud
- Objectif: exécuter les tests d'intégration/e2e/perf avec services réels.
- Exemples de services: MAX Serve, Qdrant, Redis, PostgreSQL, Neo4j.
- Règle: la CI est la source de vérité pour les comportements multi-services.

### 1.3 Production Kubernetes
- Objectif: exploitation, résilience, sécurité, observabilité, SLO.
- Règle: les décisions d'architecture runtime se valident en production-like puis production.

---

## 2) Contrat des dépendances

### 2.1 Source de vérité
- Les dépendances Python de test doivent exister offline (`vendor/wheels/`).
- L'installation doit utiliser `--no-index --find-links=vendor/wheels`.

### 2.2 Ajout d'une dépendance
1. L'agent déclare explicitement le besoin via `# Needs:`.
2. L'opérateur ajoute la dépendance dans `requirements-test.txt` (ou fichier approprié).
3. L'opérateur met à jour `vendor/wheels/`.
4. Le besoin est validé au run suivant.

### 2.3 Interdits
- `pip install` en ligne dans les flows Codex/CI.
- Téléchargement ad hoc non tracé.

---

## 3) Classification des tests

| Type | Emplacement | Environnement nominal | Services externes |
|---|---|---|---|
| unit | `tests/unit/` | Codex offline | Non |
| contract | `tests/contract/` | Codex offline | Non (doublures locales) |
| integration | `tests/integration/` | CI Docker | Oui |
| e2e | `tests/e2e/` | CI Docker | Oui |
| perf | `tests/perf/` | CI/staging dédié | Oui |

Règle stricte: un test n'est valide que dans son environnement nominal.

---

## 4) Signal vs bruit

### 4.1 Signaux valides
- Compilation/syntaxe conforme.
- Tests `unit`/`contract` passés en offline.
- Tests `integration`/`e2e` passés en CI adéquate.
- Contrats d'API respectés.
- Logs/métriques/traces attendus présents.

### 4.2 Bruit (non bloquant si hors domaine)
- Échec réseau externe en environnement offline.
- Absence de Docker en stage Codex.
- Dépendance non disponible avant son ajout au wheelhouse.
- Test exécuté hors de son domaine nominal.

Principe: bruit attendu ≠ régression produit.

---

## 5) Évolution d'architecture

- Toute évolution doit préserver les invariants de contrat (interfaces, dépendances, classification de tests).
- Les changements majeurs doivent expliciter:
  - impact runtime,
  - stratégie de migration,
  - compatibilité ascendante,
  - rollback.
- Le couplage inter-services doit rester observable, testable et réversible.

---

## 6) Contrat d'observabilité

- Chaque service critique doit exposer des signaux exploitables: logs structurés, métriques, traces.
- Les chemins critiques (chat, mémoire, RAG, gateway) doivent être corrélables bout-en-bout.
- Les alertes doivent être actionnables (symptôme + contexte minimal + piste de remédiation).

---

## 7) Contrat d'usage des agents

- Les agents appliquent ces contrats avant toute décision de tooling ou de test.
- En cas de ressource manquante: déclarer explicitement via `# Needs:` et continuer le travail sans contournement réseau.
- Les agents ne reclassifient pas arbitrairement un test pour obtenir un faux signal vert.
- Les sorties de l'agent doivent distinguer clairement:
  - ce qui est validé localement,
  - ce qui doit être validé en CI,
  - ce qui dépend d'une action opérateur.

---

## 8) Règle de gouvernance

Ce document définit les contrats fondamentaux de brainego.
En cas de conflit d'interprétation:
1. `CONTRATS.md` fait foi,
2. puis ce document (`CONTRATS_FONDAMENTAUX.md`),
3. puis les guides opérationnels.
