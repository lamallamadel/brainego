# Roadmap de Déploiement — Epics & Livrables Techniques

## Contexte

Ce document détaille la roadmap de déploiement en 4 phases (16 semaines) du produit IA self-hosted. Chaque phase est décomposée en Epics avec leurs livrables techniques attendus. L'ensemble s'inscrit dans l'architecture Kubernetes avec MAX Serve (Mojo), MCP Gateway (MCPJungle), et Memory Engine (Mem0 + Qdrant + Neo4j + Redis).

***

## Phase 1 — MVP Fonctionnel (Semaines 1–4)

> **Objectif** : Un système opérationnel capable d'ingérer des documents, stocker en mémoire vectorielle, et répondre via une API OpenAI-compatible servie par MAX.

***

### Epic 1.1 — Infrastructure de Base & Containerisation

Poser le socle Docker Compose local qui sera migré vers Kubernetes en Phase 4.

- Provisionnement d'une machine avec GPU (RTX 4090 24GB, 64GB RAM, 500GB NVMe)
- Rédaction du `docker-compose.yaml` maître regroupant tous les services (MAX Serve, Qdrant, Redis, PostgreSQL, MinIO)
- Configuration réseau Docker : bridge interne `ai-platform-net`, isolation des services
- Script d'initialisation `init.sh` : vérification GPU (nvidia-smi), pull des images, création des volumes persistants
- Documentation d'installation (README) avec pré-requis matériel et logiciel

***

### Epic 1.2 — Déploiement MAX Serve & Inférence

Rendre le moteur d'inférence Mojo/MAX opérationnel avec un premier modèle.

- Installation de Modular MAX via `pip install modular`
- Déploiement de Llama 3.3 8B Instruct (GGUF Q4_K_M) via `max serve`
- Validation de l'endpoint `/v1/chat/completions` (compatibilité OpenAI)
- Configuration du batching (max batch size 32) et des limites mémoire GPU
- Tests de charge : mesure latency P50/P95/P99, throughput tokens/sec
- Health check endpoint `/health` fonctionnel avec réponse JSON structurée

***

### Epic 1.3 — Pipeline RAG Core

Construire la chaîne complète Ingestion → Embedding → Retrieval → Génération.

- Déploiement de Qdrant (Docker, volume persistant, port 6333)
- Développement du service d'ingestion Python : chunking (1 000 caractères, overlap 100), metadata tagging (source, date, projet, catégorie)
- Intégration du modèle d'embedding Nomic Embed v1.5 (servi localement via MAX)
- Développement du retriever : recherche par similarité cosinus, top-k configurable (défaut k=5), filtrage par métadonnées
- Endpoint API `/v1/rag/query` : reçoit une question, retrieves le contexte, génère la réponse augmentée
- Tests unitaires et d'intégration sur le pipeline complet (pytest)

***

### Epic 1.4 — Mémoire Persistante Mem0

Initialiser la couche mémoire qui persiste entre les sessions.

- Déploiement de Mem0 open-source (Docker) connecté à Qdrant comme backend vectoriel
- Déploiement Redis (Docker) pour le stockage clé-valeur des faits et préférences
- Configuration de l'extraction automatique de faits depuis les conversations
- API mémoire : `POST /memory/add`, `GET /memory/search`, `DELETE /memory/forget`
- Scoring de pertinence basique : similarité cosinus + décroissance temporelle
- Tests de persistance : redémarrage des containers → vérification de la rétention

***

### Epic 1.5 — API Unifiée & Tests End-to-End

Exposer un point d'entrée unique et valider le flux complet.

- Service API gateway léger (FastAPI) : routing vers MAX Serve, RAG, et Mem0
- Authentification basique (API key) pour le MVP
- Endpoint `/v1/chat` unifié : intègre mémoire + RAG + inférence en un seul appel
- Collection Postman / fichier `.http` avec tous les scénarios de test
- Test end-to-end : ajout d'un document → question sur ce document → réponse correcte avec contexte
- Benchmark MVP : latence cible < 3s pour une requête RAG complète

***

## Phase 2 — Intégrations & Intelligence (Semaines 5–8)

> **Objectif** : Connecter les sources de données externes via MCP, implémenter le routage multi-modèle, et structurer les connaissances en graphe.

***

### Epic 2.1 — MCP Gateway (MCPJungle)

Déployer le gateway MCP et enregistrer les premiers serveurs d'outils.

- Déploiement MCPJungle (Docker) avec authentification activée
- Enregistrement des serveurs MCP prioritaires : `mcp-github`, `mcp-notion`, `mcp-filesystem`
- Configuration des ACLs : définition des rôles agent et des permissions par serveur
- Endpoint unique `/mcp` exposé et testé depuis le service d'orchestration
- Activation OpenTelemetry pour le tracing des appels MCP
- Documentation des schémas de chaque tool exposé (JSON Schema)

***

### Epic 2.2 — Serveurs MCP Applicatifs

Déployer et configurer les connecteurs vers les outils du quotidien.

- `mcp-github` : accès repos, issues, PRs, commits (token PAT, scope configuré)
- `mcp-notion` : accès pages, databases, blocs (OAuth integration token)
- `mcp-slack` : lecture de channels, messages, threads (Bot token, event subscriptions)
- `mcp-gmail` : lecture emails, extraction de tâches (OAuth 2.0, scopes read-only)
- `mcp-calendar` : événements, deadlines (Google Calendar API, OAuth 2.0)
- Tests d'intégration par serveur : appel tool → réponse structurée → validation du schéma

***

### Epic 2.3 — Agent Router & Multi-Modèle

Implémenter la logique de sélection automatique du modèle optimal par requête.

- Déploiement de Qwen 2.5 Coder 7B et DeepSeek R1 7B en parallèle sur MAX Serve
- Développement du classifieur d'intent (code, raisonnement, général, créatif)
- Logique de routing : intent → modèle (code→Qwen, reasoning→DeepSeek, default→Llama)
- Fallback automatique : si le modèle principal est surchargé, basculer sur le suivant
- Métriques de routing : compteur par modèle, latence par modèle, taux de fallback
- Configuration déclarative YAML du routing (pas de hardcoding)

***

### Epic 2.4 — Knowledge Graph (Neo4j)

Structurer les relations entre projets, concepts, personnes et événements.

- Déploiement Neo4j Community (Docker, volume persistant, port 7687)
- Définition du schéma de graphe : nœuds (Project, Person, Concept, Document, Problem, Lesson), relations (WORKS_ON, RELATES_TO, CAUSED_BY, SOLVED_BY, LEARNED_FROM)
- Pipeline NER (Named Entity Recognition) : extraction automatique d'entités depuis les documents ingérés
- Pipeline de construction de relations : co-occurrence, extraction explicite, inference
- API graphe : `POST /graph/query` (Cypher), `GET /graph/neighbors/{entity}`
- Intégration avec le retriever RAG : enrichissement des résultats vectoriels avec le contexte relationnel du graphe

***

### Epic 2.5 — Budget Memory Dynamique

Implémenter l'allocation intelligente de contexte par requête.

- Module `MemoryBudgetAllocator` : estimation de complexité → répartition des tokens (working, project, long-term, RAG)
- Scoring Mem0 complet : pertinence (cosinus) × importance (fréquence) × fraîcheur (decay exponentiel)
- Mécanisme de promotion/démission : les souvenirs fréquemment utiles gagnent en importance, les inutilisés déclinent
- Configuration des budgets par défaut et overrides par workspace
- Tests A/B : comparer la qualité des réponses avec budget fixe vs dynamique
- Logging des allocations pour analyse et optimisation future

***

## Phase 3 — Learning Automatique (Semaines 9–12)

> **Objectif** : Rendre le système auto-évolutif avec fine-tuning incrémental, détection de drift, et boucle de feedback.

***

### Epic 3.1 — Pipeline de Collecte Automatique

Automatiser l'ingestion continue depuis toutes les sources connectées.

- CronJob de synchronisation : GitHub (toutes les 6h), Notion (toutes les 4h), Slack (toutes les 2h)
- Service de normalisation : conversion de tous les formats en chunks standardisés avec métadonnées uniformes
- Déduplication : hash-based (exact) + similarité cosinus (near-duplicate, seuil > 0.95)
- File d'attente d'ingestion (Redis Queue) : buffer les documents en cas de pic de collecte
- Dashboard de monitoring : nombre de documents par source, statut d'indexation, erreurs
- Webhook endpoints pour ingestion en temps réel (push depuis GitHub, Notion)

***

### Epic 3.2 — Fine-Tuning EWC/LoRA Incrémental

Implémenter le pipeline d'apprentissage continu qui protège les connaissances existantes.

- Service `learning-engine` (Python, PyTorch) avec calcul de la Fisher Information Matrix sur le dataset courant
- Pipeline LoRA : extraction des interactions/feedbacks de la semaine → formatage dataset → fine-tune LoRA rank-16
- Régularisation EWC : application de la pénalité \(\frac{\lambda}{2} \sum_i F_i(\theta_i - \theta^*_i)^2\) pendant le fine-tuning
- Sauvegarde des adapters LoRA sur MinIO (S3-compatible) avec versioning sémantique (v1.0, v1.1...)
- Hot-swap des adapters LoRA sur MAX Serve sans redémarrage du service d'inférence
- CronJob Kubernetes `weekly-finetune` : déclenché chaque dimanche 02:00 UTC

***

### Epic 3.3 — Détection de Drift & Triggers

Monitorer automatiquement la qualité et déclencher les ré-apprentissages.

- Module `DriftMonitor` : calcul KL Divergence sur les embeddings des requêtes (fenêtre glissante 7 jours vs 7 jours précédents)
- Module PSI (Population Stability Index) : stabilité de la distribution des intents
- Seuils configurables en YAML : `kl_threshold: 0.1`, `psi_threshold: 0.2`, `accuracy_min: 0.75`
- Actions automatiques : drift détecté → alerte Slack + déclenchement pipeline fine-tune
- Tableau de bord Grafana : évolution de la KL Divergence, PSI, et accuracy au fil du temps
- Logging structuré de chaque détection pour analyse post-mortem

***

### Epic 3.4 — Feedback Loop & Scoring de Qualité

Capturer le feedback utilisateur pour améliorer le modèle.

- Boutons 👍/👎 sur chaque réponse dans la Web UI + API `POST /v1/feedback`
- Stockage des feedbacks en PostgreSQL : query, response, model, memory_used, tools_called, rating, timestamp
- Calcul automatique de l'accuracy par modèle, par type d'intent, par projet
- Pondération des données de fine-tuning : les réponses 👍 ont un poids 2x, les 👎 un poids 0.5x (pour apprendre à éviter)
- Export hebdomadaire du dataset de fine-tuning : interactions filtrées par qualité
- Rapport mensuel automatique : évolution de la qualité, modèles les plus performants, sujets problématiques

***

### Epic 3.5 — Meta-Learning Cross-Projets

Permettre au système de s'adapter plus vite à chaque nouveau projet en apprenant des patterns transversaux.

- Implémentation MAML (Model-Agnostic Meta-Learning) : extraction de tâches par projet, optimisation du point d'initialisation
- Dataset de méta-tâches : chaque projet = une tâche, avec ses documents, feedbacks, et patterns
- Pipeline mensuel `meta-learning-update` : CronJob le 1er de chaque mois
- Métriques d'adaptation : nombre de steps nécessaires pour atteindre 80% accuracy sur un nouveau projet (cible : < 10 steps)
- Stockage des meta-weights sur MinIO avec versioning
- Replay buffer pondéré : les échecs (plans non réussis) reçoivent un poids 3x pour renforcer l'apprentissage des erreurs

***

## Phase 4 — Production Hardening (Semaines 13–16)

> **Objectif** : Migrer sur Kubernetes, sécuriser, observer, et rendre le système résilient pour un fonctionnement 24/7.

***

### Epic 4.1 — Migration Kubernetes

Transformer le déploiement Docker Compose en cluster Kubernetes production.

- Installation K3s (lightweight Kubernetes) sur les nodes GPU et CPU
- Rédaction du Helm chart `ai-platform` avec toutes les dépendances (voir structure dans le rapport d'architecture)
- StatefulSets pour les services stateful : Qdrant, Neo4j, PostgreSQL, Redis (avec PersistentVolumeClaims)
- Deployments pour les services stateless : MAX Serve, MCPJungle, Agent Router, Mem0, Learning Engine
- HPA (Horizontal Pod Autoscaler) sur MAX Serve : scaling sur `cpu_utilization > 70%` et `inference_queue_depth > 10`
- Pod Disruption Budgets : `minAvailable: 1` sur chaque service critique
- Script de migration : export des données Docker volumes → import dans PVCs Kubernetes

***

### Epic 4.2 — API Gateway & Sécurité

Implémenter le point d'entrée sécurisé et la gestion des accès.

- Déploiement Kong Ingress Controller sur Kubernetes
- Configuration OAuth 2.1 : issuer local (Keycloak) ou externe, tokens JWT RS256
- Rate limiting multi-couche : par IP (100 req/min), par user (1 000 req/h), par workspace (token budget quotidien)
- TLS 1.3 avec Let's Encrypt (cert-manager) et HSTS
- Network Policies Kubernetes : isolation `ai-platform` namespace, whitelist des flux inter-pods
- RBAC Kubernetes : service accounts dédiés par pod, least-privilege
- Secrets management : Kubernetes Secrets chiffrés at-rest (ou HashiCorp Vault si disponible)
- Audit log : chaque requête loggée avec user, tokens consommés, latence, modèle, outils MCP appelés

***

### Epic 4.3 — Observabilité Complète

Mettre en place la visibilité totale sur le système.

- Déploiement Prometheus (scrape toutes les 15s) + Grafana (dashboards pré-configurés)
- Déploiement OpenTelemetry Collector : tracing distribué de bout en bout (API Gateway → Agent Router → MAX Serve → MCP → Memory)
- Déploiement Loki : agrégation des logs structurés JSON de tous les services, rétention 90 jours
- Dashboard Grafana « Platform Overview » : latence P99, error rate, GPU utilisation, token usage, mémoire hit rate
- Dashboard Grafana « Learning Engine » : KL Divergence, PSI, accuracy, LoRA versions actives
- Dashboard Grafana « MCP Activity » : appels par serveur, latence par tool, erreurs
- Alerting : Prometheus AlertManager → Slack (latency > 2s, error rate > 1%, GPU > 90%, drift detected, budget exceeded)

***

### Epic 4.4 — Résilience & Fault Tolerance

Garantir le fonctionnement continu même en cas de défaillance partielle.

- Circuit breakers sur chaque appel inter-service (timeout 5s, threshold 3 failures, recovery 30s)
- Fallback chain complète : MAX GPU → Ollama CPU → réponse cache → message de dégradation gracieuse
- Liveness probes (restart si unhealthy) + Readiness probes (retrait du load balancer si non prêt) sur chaque pod
- Anti-affinity rules : répartir les replicas de MAX Serve et MCPJungle sur des nodes différents
- Graceful shutdown : drain des requêtes en cours (30s terminationGracePeriodSeconds)
- Backup automatique quotidien : Qdrant snapshots, Neo4j dump, PostgreSQL pg_dump → MinIO (rétention 30 jours)
- Runbook de disaster recovery : procédure documentée de restauration complète depuis les backups

***

### Epic 4.5 — Validation & Mise en Production

Valider la robustesse du système avant le go-live.

- Tests de charge : k6 ou Locust, scénario réaliste (50 utilisateurs concurrents, mix requêtes chat/RAG/MCP)
- Chaos engineering : injection de pannes (kill pod aléatoire, saturation CPU, network partition) → validation des circuit breakers et fallbacks
- Security audit : scan de vulnérabilités des images Docker (Trivy), test de pénétration sur l'API Gateway
- Test de migration de données : backup complet → restauration sur un cluster vierge → validation intégrité
- Documentation opérationnelle : architecture decision records (ADR), runbooks, procédures d'escalade
- Définition des SLOs (Service Level Objectives) : disponibilité 99.5%, latence P99 < 2s, perte de données 0
- Go/No-Go checklist signée : toutes les métriques dans les seuils → mise en production