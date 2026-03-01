# Pilot Readiness Runbook (AFR-96)

## Goal

Onboard a pilot team in **under 2 hours** with a reproducible flow that covers:

1. Workspace setup
2. MCP connection
3. Repository indexing for RAG demos
4. RBAC and policy validation
5. Incident handling drill
6. Demo execution scripts

This runbook consolidates existing platform docs into one operator checklist.

---

## Success Criteria

- Pilot environment is reachable (`api-server`, `mcpjungle-gateway`, dependencies).
- MCP gateway is connected and responds to server/tool discovery.
- A representative subset of repo documents is indexed into RAG.
- RBAC/policy enforcement is validated with at least one expected deny case.
- Incident drill is executed and evidence is captured.
- The full flow can be completed in <2 hours by a new operator.

---

## Timebox (Target: 100-120 minutes)

| Phase | Target | Output |
|---|---:|---|
| 0. Preflight | 10 min | Environment and config checks passed |
| 1. Start services | 20 min | Healthy API + MCP gateway |
| 2. MCP connectivity | 15 min | MCP servers and ACL role verified |
| 3. Repo indexing | 20 min | Batch ingestion + search verification |
| 4. RBAC/policy validation | 20 min | Read allowed, write denied (expected) |
| 5. Incident drill | 20 min | Incident evidence artifacts produced |
| Buffer | 15 min | Troubleshooting margin |

---

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- `curl`
- Optional for full MCP external integrations:
  - `GITHUB_TOKEN`
  - `NOTION_API_KEY`

Recommended environment variables:

```bash
export API_KEYS="sk-test-key-123,sk-admin-key-456,sk-dev-key-789,sk-project-agent-key-321"
export WORKSPACE_IDS="default,pilot"
```

---

## 0) Preflight

Run baseline checks:

```bash
bash scripts/pilot/pilot_preflight.sh
```

If services are already started, include runtime health checks:

```bash
bash scripts/pilot/pilot_preflight.sh --check-health
```

---

## 1) Start/Verify Services

Start core services:

```bash
docker compose up -d api-server mcpjungle-gateway qdrant redis
```

Quick health checks:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:9100/health
curl -fsS http://localhost:6333/health
```

---

## 2) Validate MCP Connectivity + RBAC

Run automated MCP and RBAC checks:

```bash
python scripts/pilot/demo_mcp_rbac_policy.py \
  --gateway-url http://localhost:9100
```

What this validates:

- Gateway health
- Admin and analyst role mapping
- Server discovery for analyst role
- Tool discovery for analyst role
- Expected deny on write action (`write_file`) for analyst

---

## 3) Index Repository Content for Demo

Index curated repo documents into RAG:

```bash
python scripts/pilot/demo_repo_index.py \
  --api-url http://localhost:8000 \
  --workspace-id default \
  --api-key sk-test-key-123
```

Default index set:

- `README.md`
- `QUICKSTART.md`
- `MCP_QUICKSTART.md`
- `SECURITY_QUICKSTART.md`
- `DISASTER_RECOVERY_RUNBOOK.md`
- `MCP_AFR32_MANUAL_TEST.md`

The script runs a follow-up search to confirm retrievability.

---

## 3b) Optional: Repo-RAG Golden Set Spot Check (AFR-111)

Use the 20-question golden set to validate retrieval relevance and citation correctness:

- Golden set: `tests/contract/fixtures/repo_rag_golden_set.ndjson`
- Guide: `docs/repo_rag_golden_set.md`

Recommended usage:

1. Keep the indexed pilot corpus from step 3.
2. Run a sample of 5-10 golden questions first.
3. Ensure answers include source citations in `[source:<path>]` format.

---

## 4) Validate Policy + Incident Handling Drill

Execute a short incident drill:

```bash
bash scripts/pilot/demo_incident_drill.sh \
  --gateway-url http://localhost:9100 \
  --api-url http://localhost:8000 \
  --workspace-id default \
  --analyst-key sk-test-key-123 \
  --api-key sk-test-key-123
```

Drill behavior:

1. Snapshot key health endpoints
2. Trigger a controlled policy deny (write attempt with analyst role)
3. Export recent audit events when API auth permits it
4. Save artifacts to `artifacts/pilot_incident/<timestamp>/`

---

## 5) One-Command Pilot Demo

Run the full scripted flow:

```bash
bash scripts/pilot/run_pilot_demo.sh
```

Useful options:

```bash
bash scripts/pilot/run_pilot_demo.sh --check-health
bash scripts/pilot/run_pilot_demo.sh --skip-index
bash scripts/pilot/run_pilot_demo.sh --skip-incident
```

---

## Evidence Checklist (Sign-off)

- [ ] `pilot_preflight.sh` exited with code 0
- [ ] `demo_mcp_rbac_policy.py` exited with code 0
- [ ] `demo_repo_index.py` exited with code 0 (or approved skip)
- [ ] `demo_incident_drill.sh` exited with code 0
- [ ] Artifact folder created under `artifacts/pilot_incident/`
- [ ] Demo operator confirms completion time < 2 hours

---

## Troubleshooting Quick Notes

- **401/403 on API endpoints**  
  Ensure `API_KEYS` contains the key used by scripts and service was restarted.

- **`workspace_id_missing` errors**  
  Provide `X-Workspace-Id` header (scripts already do this).

- **MCP server unavailable**  
  Check Node.js availability and gateway logs:
  `docker compose logs -f mcpjungle-gateway`

- **Indexing fails**  
  Verify `api-server` + `qdrant` health and inspect:
  `docker compose logs -f api-server qdrant`

---

## Related Documents

- `MCP_QUICKSTART.md`
- `MCP_AFR32_MANUAL_TEST.md`
- `SECURITY_QUICKSTART.md`
- `DISASTER_RECOVERY_RUNBOOK.md`
- `docs/repo_rag_golden_set.md`
- `configs/mcp-acl.yaml`
- `configs/tool-policy.yaml`
