# Pilot Onboarding Runbook (AFR-118)

## Goal

Onboard a pilot team in **under 2 hours** with a reproducible, auditable flow that covers:

1. Connect **GitHub + issue tracker** (Linear by default, Jira as alternative)
2. Configure and verify **MCP policy guardrails**
3. Index repository docs for RAG demo queries
4. Validate RBAC behavior (allow/deny paths)
5. Run pilot demo scenarios end-to-end
6. Execute rollback safely if pilot settings must be reverted

This runbook keeps compatibility with existing pilot scripts from AFR-96 while adding onboarding controls required by AFR-118.

---

## Success Criteria

- Pilot environment is reachable (`api-server`, `mcpjungle-gateway`, dependencies).
- GitHub and at least one tracker connector (Linear or Jira) are reachable through MCP.
- Policy files are configured with least privilege and test scope restrictions.
- RBAC denies at least one forbidden write action as expected.
- A representative subset of repository docs is indexed and retrievable through RAG.
- Demo scenarios run successfully and evidence artifacts are stored.
- Rollback procedure is documented and validated (config restore + health checks).

---

## Timebox (Target: 100-120 minutes)

| Phase | Target | Output |
|---|---:|---|
| 0. Preflight + backup | 10 min | Baseline checks passed, rollback snapshot captured |
| 1. Start services | 15 min | Healthy API + gateway + Qdrant |
| 2. Connect GitHub + tracker | 20 min | MCP discovery and read smoke tests pass |
| 3. Configure policies | 15 min | ACL + tool policy aligned to pilot scope |
| 4. RBAC validation | 15 min | Expected deny behavior proven |
| 5. Repo indexing | 15 min | Batch ingest + retrieval verification |
| 6. Demo scenarios | 20 min | End-to-end evidence for pilot walkthrough |
| 7. Rollback rehearsal | 10 min | Config restore path validated |

---

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- `curl`
- `jq` (recommended for readable JSON responses)

Required connector credentials (minimum):

- `GITHUB_TOKEN`
- One tracker integration:
  - `LINEAR_API_KEY` (preferred), or
  - `JIRA_BASE_URL` + `JIRA_EMAIL` + `JIRA_API_TOKEN`

Recommended pilot environment variables:

```bash
export API_KEYS="sk-test-key-123,sk-admin-key-456,sk-dev-key-789,sk-project-agent-key-321"
export WORKSPACE_IDS="default,pilot"
export PILOT_WORKSPACE_ID="pilot"
```

> Do not commit secrets. Keep `.env.mcpjungle` local and managed via secure secret handling in production.

---

## Files Used by This Runbook

- `.env.mcpjungle`
- `configs/mcp-servers.yaml`
- `configs/mcp-acl.yaml`
- `configs/tool-policy.yaml`
- `scripts/pilot/pilot_preflight.sh`
- `scripts/pilot/demo_mcp_rbac_policy.py`
- `scripts/pilot/demo_repo_index.py`
- `scripts/pilot/demo_incident_drill.sh`
- `scripts/pilot/run_pilot_demo.sh`

---

## 0) Preflight + Rollback Snapshot

Run baseline checks:

```bash
bash scripts/pilot/pilot_preflight.sh --strict-env
```

Start services if needed:

```bash
docker compose up -d api-server mcpjungle-gateway qdrant redis
```

Capture rollback snapshot **before** policy edits:

```bash
ts="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="artifacts/pilot_config_backup/${ts}"
mkdir -p "${backup_dir}"
cp .env.mcpjungle "${backup_dir}/.env.mcpjungle" 2>/dev/null || true
cp configs/mcp-servers.yaml configs/mcp-acl.yaml configs/tool-policy.yaml "${backup_dir}/"
echo "Backup saved to ${backup_dir}"
```

Optional runtime health checks:

```bash
bash scripts/pilot/pilot_preflight.sh --check-health
```

---

## 1) Connect GitHub + Tracker

### 1.1 Configure credentials

Initialize local env file:

```bash
cp .env.mcpjungle.example .env.mcpjungle
```

Set at least:

```bash
# GitHub
GITHUB_TOKEN=...
GITHUB_TEST_OWNER=...
GITHUB_TEST_REPO_1=...
GITHUB_TEST_REPO_2=...

# Tracker (choose one)
LINEAR_API_KEY=...
# OR
JIRA_BASE_URL=...
JIRA_EMAIL=...
JIRA_API_TOKEN=...
```

### 1.2 Restart gateway with updated env

```bash
docker compose up -d mcpjungle-gateway
curl -fsS http://localhost:9100/health | jq .
```

### 1.3 Validate MCP server discovery

```bash
curl -fsS \
  -H "Authorization: Bearer sk-dev-key-789" \
  http://localhost:9100/mcp/servers | jq .
```

Expected:

- `mcp-github` present
- `mcp-linear` and/or `mcp-jira` present (according to configured tracker)

### 1.4 GitHub read smoke test

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer sk-dev-key-789" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/call \
  -d '{
    "server_id":"mcp-github",
    "tool_name":"github_get_repository",
    "arguments":{"owner":"'"${GITHUB_TEST_OWNER}"'","repo":"'"${GITHUB_TEST_REPO_1}"'"}
  }' | jq .
```

Expected: response includes repository metadata and no tool error.

### 1.5 Tracker read smoke test (Linear or Jira)

Linear:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer sk-dev-key-789" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/call \
  -d '{"server_id":"mcp-linear","tool_name":"linear_list_teams","arguments":{}}' | jq .
```

Jira:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer sk-dev-key-789" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/call \
  -d '{"server_id":"mcp-jira","tool_name":"jira_list_projects","arguments":{}}' | jq .
```

Expected: tracker entities are listed without authentication errors.

---

## 2) Configure Policy Guardrails

Configure least privilege for pilot scope:

1. **`configs/mcp-servers.yaml`**
   - Keep GitHub restricted to test owner/repos (`allowed_repositories`, `allowed_owners`)
   - Ensure tracker operations are scoped (`read/list/get/search/create/update`)
   - Keep destructive operations denied when possible

2. **`configs/mcp-acl.yaml`**
   - Validate API key role mappings (`admin`, `developer`, `analyst`, `project-agent`)
   - Ensure `analyst` is read-only
   - Ensure `developer` has tracker write but GitHub read-only

3. **`configs/tool-policy.yaml`**
   - Keep write allowlist scoped to tracker write tools only
   - Keep required write scopes enabled:
     - `mcp.tool.write`
     - `mcp.issue_tracker.write`

Apply changes:

```bash
docker compose restart mcpjungle-gateway
curl -fsS http://localhost:9100/health | jq .
```

---

## 3) Validate RBAC + Policy Enforcement

Run automated pilot RBAC checks:

```bash
python3 scripts/pilot/demo_mcp_rbac_policy.py \
  --gateway-url http://localhost:9100 \
  --admin-key sk-admin-key-456 \
  --analyst-key sk-test-key-123
```

Manual role inspection:

```bash
curl -fsS -H "Authorization: Bearer sk-admin-key-456" \
  http://localhost:9100/mcp/acl/role | jq .

curl -fsS -H "Authorization: Bearer sk-test-key-123" \
  http://localhost:9100/mcp/acl/role | jq .
```

Expected deny case (analyst write must fail):

```bash
curl -sS -o /tmp/pilot_rbac_deny.json -w "%{http_code}\n" \
  -X POST http://localhost:9100/mcp/tools/call \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id":"mcp-filesystem",
    "tool_name":"write_file",
    "arguments":{"path":"/workspace/pilot_forbidden_write.txt","content":"deny expected"}
  }'
```

Expected HTTP status: `403`.

---

## 4) Index Repository Content for Demo

Index curated repository docs into RAG (use isolated pilot workspace):

```bash
python3 scripts/pilot/demo_repo_index.py \
  --api-url http://localhost:8000 \
  --workspace-id "${PILOT_WORKSPACE_ID:-pilot}" \
  --api-key sk-test-key-123
```

Default index set:

- `README.md`
- `QUICKSTART.md`
- `MCP_QUICKSTART.md`
- `SECURITY_QUICKSTART.md`
- `DISASTER_RECOVERY_RUNBOOK.md`
- `MCP_AFR32_MANUAL_TEST.md`

The script performs a follow-up retrieval query to validate indexing success.

---

## 5) Run Demo Scenarios

### Scenario A - Connector walkthrough (GitHub + tracker)

- Show server discovery (`/mcp/servers`)
- Run one GitHub read call (`github_get_repository`)
- Run one tracker read call (`linear_list_teams` or `jira_list_projects`)

### Scenario B - Security/RBAC walkthrough

Run:

```bash
python3 scripts/pilot/demo_mcp_rbac_policy.py --gateway-url http://localhost:9100
```

Show expected deny behavior for analyst write action.

### Scenario C - Incident handling drill

```bash
bash scripts/pilot/demo_incident_drill.sh \
  --gateway-url http://localhost:9100 \
  --api-url http://localhost:8000 \
  --workspace-id "${PILOT_WORKSPACE_ID:-pilot}" \
  --analyst-key sk-test-key-123 \
  --api-key sk-test-key-123
```

Artifacts are written under `artifacts/pilot_incident/<timestamp>/`.

### One-command scripted flow (baseline)

```bash
bash scripts/pilot/run_pilot_demo.sh --check-health --workspace-id "${PILOT_WORKSPACE_ID:-pilot}"
```

> `run_pilot_demo.sh` covers preflight, RBAC check, repo indexing, and incident drill.  
> Keep Scenario A (GitHub + tracker connector walkthrough) as an explicit onboarding step.

---

## 6) Rollback Procedure

### Level 1 - Credential rollback

Use when external connector tokens must be revoked/removed.

1. Restore `.env.mcpjungle` from backup snapshot (or clear connector credentials)
2. Restart gateway
3. Verify only expected servers remain functional

```bash
cp artifacts/pilot_config_backup/<timestamp>/.env.mcpjungle .env.mcpjungle
docker compose restart mcpjungle-gateway
curl -fsS http://localhost:9100/health | jq .
```

### Level 2 - Policy/config rollback

Use when ACL/tool policy changes caused incorrect authorization behavior.

```bash
backup_dir="artifacts/pilot_config_backup/<timestamp>"
cp "${backup_dir}/mcp-servers.yaml" configs/mcp-servers.yaml
cp "${backup_dir}/mcp-acl.yaml" configs/mcp-acl.yaml
cp "${backup_dir}/tool-policy.yaml" configs/tool-policy.yaml
docker compose restart mcpjungle-gateway
python3 scripts/pilot/demo_mcp_rbac_policy.py --gateway-url http://localhost:9100
```

### Level 3 - Pilot data rollback (RAG workspace isolation)

Recommended strategy: keep pilot data in workspace `pilot`, then disable pilot workspace access when rollback is required.

1. Remove `pilot` from allowed workspace list
2. Restart API server
3. Verify non-pilot workspace behavior is unchanged

```bash
# Example: set WORKSPACE_IDS=default in your env/runtime config
docker compose restart api-server
curl -fsS http://localhost:8000/health | jq .
```

If individual document IDs were captured during ingest, remove them explicitly:

```bash
curl -fsS -X DELETE \
  "http://localhost:8000/v1/rag/documents/<document_id>" \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "X-API-Key: sk-test-key-123" \
  -H "X-Workspace-Id: ${PILOT_WORKSPACE_ID:-pilot}"
```

### Post-rollback verification checklist

- [ ] `/health` is green for `api-server` and `mcpjungle-gateway`
- [ ] `demo_mcp_rbac_policy.py` passes baseline checks
- [ ] Analyst write attempts are denied (`403`)
- [ ] GitHub/tracker access reflects intended scope after rollback

---

## Evidence Checklist (Sign-off)

- [ ] `pilot_preflight.sh --strict-env` exited with code 0
- [ ] GitHub connector read smoke test succeeded
- [ ] Tracker connector read smoke test succeeded (Linear or Jira)
- [ ] Policy files reviewed and gateway restarted successfully
- [ ] `demo_mcp_rbac_policy.py` exited with code 0
- [ ] `demo_repo_index.py` exited with code 0
- [ ] `demo_incident_drill.sh` exited with code 0
- [ ] Incident artifact folder created in `artifacts/pilot_incident/`
- [ ] Rollback snapshot created in `artifacts/pilot_config_backup/`
- [ ] Operator confirms onboarding flow completed in < 2 hours

---

## Troubleshooting Quick Notes

- **401/403 from MCP gateway**  
  Verify API key role mapping in `configs/mcp-acl.yaml` and restart gateway.

- **GitHub tool failures**  
  Confirm `GITHUB_TOKEN` scope and test repository allowlist in `configs/mcp-servers.yaml`.

- **Linear/Jira not visible in `/mcp/servers`**  
  Verify corresponding credentials in `.env.mcpjungle` and connector `enabled: true`.

- **`workspace_id_missing` errors on RAG endpoints**  
  Provide `X-Workspace-Id` header (script handles this automatically).

- **RBAC deny test does not return 403**  
  Re-check `configs/mcp-acl.yaml` + `configs/tool-policy.yaml`, then restart gateway.

- **Indexing failures**  
  Verify `api-server` + `qdrant` health and inspect logs:
  `docker compose logs -f api-server qdrant`

---

## Related Documents

- `MCP_QUICKSTART.md`
- `MCP_INTEGRATIONS.md`
- `MCP_AFR32_MANUAL_TEST.md`
- `SECURITY_QUICKSTART.md`
- `DISASTER_RECOVERY_RUNBOOK.md`
- `configs/mcp-servers.yaml`
- `configs/mcp-acl.yaml`
- `configs/tool-policy.yaml`
