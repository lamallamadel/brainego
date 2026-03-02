#!/usr/bin/env bash
# Orchestrate pilot readiness demo flow (AFR-96).

set -euo pipefail

CHECK_HEALTH=0
SKIP_INDEX=0
SKIP_INCIDENT=0

GATEWAY_URL="http://localhost:9100"
API_URL="http://localhost:8000"
WORKSPACE_ID="${PILOT_WORKSPACE_ID:-default}"
ADMIN_KEY="${PILOT_ADMIN_KEY:-sk-admin-key-456}"
ANALYST_KEY="${PILOT_ANALYST_KEY:-sk-test-key-123}"
API_KEY="${PILOT_API_KEY:-sk-test-key-123}"

usage() {
  cat <<'EOF'
Usage: bash scripts/pilot/run_pilot_demo.sh [options]

Options:
  --check-health      Include runtime health checks in preflight
  --skip-index        Skip repository indexing demo
  --skip-incident     Skip incident drill
  --gateway-url URL   MCP gateway URL (default: http://localhost:9100)
  --api-url URL       API server URL (default: http://localhost:8000)
  --workspace-id ID   Workspace ID (default: default)
  --admin-key KEY     Admin API key
  --analyst-key KEY   Analyst API key
  --api-key KEY       API key for RAG indexing + audit export
  -h, --help          Show this help
EOF
}

while (($#)); do
  case "$1" in
    --check-health)
      CHECK_HEALTH=1
      shift
      ;;
    --skip-index)
      SKIP_INDEX=1
      shift
      ;;
    --skip-incident)
      SKIP_INCIDENT=1
      shift
      ;;
    --gateway-url)
      GATEWAY_URL="$2"
      shift 2
      ;;
    --api-url)
      API_URL="$2"
      shift 2
      ;;
    --workspace-id)
      WORKSPACE_ID="$2"
      shift 2
      ;;
    --admin-key)
      ADMIN_KEY="$2"
      shift 2
      ;;
    --analyst-key)
      ANALYST_KEY="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 2
      ;;
  esac
done

echo "=== Pilot Demo Runner (AFR-96) ==="
echo "gateway_url=${GATEWAY_URL}"
echo "api_url=${API_URL}"
echo "workspace_id=${WORKSPACE_ID}"
echo ""

if [[ "$CHECK_HEALTH" -eq 1 ]]; then
  bash scripts/pilot/pilot_preflight.sh --check-health
else
  bash scripts/pilot/pilot_preflight.sh
fi

echo ""
python3 scripts/pilot/demo_mcp_rbac_policy.py \
  --gateway-url "${GATEWAY_URL}" \
  --admin-key "${ADMIN_KEY}" \
  --analyst-key "${ANALYST_KEY}"

if [[ "$SKIP_INDEX" -eq 0 ]]; then
  echo ""
  python3 scripts/pilot/demo_repo_index.py \
    --api-url "${API_URL}" \
    --workspace-id "${WORKSPACE_ID}" \
    --api-key "${API_KEY}"
else
  echo ""
  echo "[INFO] Skipping repo indexing step"
fi

if [[ "$SKIP_INCIDENT" -eq 0 ]]; then
  echo ""
  bash scripts/pilot/demo_incident_drill.sh \
    --gateway-url "${GATEWAY_URL}" \
    --api-url "${API_URL}" \
    --workspace-id "${WORKSPACE_ID}" \
    --analyst-key "${ANALYST_KEY}" \
    --api-key "${API_KEY}"
else
  echo ""
  echo "[INFO] Skipping incident drill step"
fi

echo ""
echo "=== Pilot demo completed successfully ==="
