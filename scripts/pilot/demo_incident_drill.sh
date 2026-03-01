#!/usr/bin/env bash
# Pilot demo: incident handling drill with evidence artifacts (AFR-96).

set -euo pipefail

GATEWAY_URL="http://localhost:9100"
API_URL="http://localhost:8000"
WORKSPACE_ID="default"
ANALYST_KEY="${PILOT_ANALYST_KEY:-sk-test-key-123}"
API_KEY="${PILOT_API_KEY:-sk-test-key-123}"
OUTPUT_DIR="artifacts/pilot_incident"
TIMEOUT_SECONDS=10
SKIP_AUDIT=0

PASSED=0
WARNINGS=0
FAILED=0

usage() {
  cat <<'EOF'
Usage: bash scripts/pilot/demo_incident_drill.sh [options]

Options:
  --gateway-url URL     MCP gateway URL (default: http://localhost:9100)
  --api-url URL         API server URL (default: http://localhost:8000)
  --workspace-id ID     Workspace ID (default: default)
  --analyst-key KEY     Analyst API key for deny test
  --api-key KEY         API key for audit export
  --output-dir PATH     Artifact output root (default: artifacts/pilot_incident)
  --timeout SECONDS     HTTP timeout per request (default: 10)
  --skip-audit          Skip /audit export step
  -h, --help            Show this help
EOF
}

while (($#)); do
  case "$1" in
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
    --analyst-key)
      ANALYST_KEY="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --skip-audit)
      SKIP_AUDIT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[FAIL] Unknown option: $1"
      usage
      exit 2
      ;;
  esac
done

pass() {
  echo "[PASS] $1"
  PASSED=$((PASSED + 1))
}

warn() {
  echo "[WARN] $1"
  WARNINGS=$((WARNINGS + 1))
}

fail() {
  echo "[FAIL] $1"
  FAILED=$((FAILED + 1))
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
run_dir="${OUTPUT_DIR%/}/${timestamp}"
mkdir -p "$run_dir"

echo "=== Pilot Incident Drill (AFR-96) ==="
echo "Artifacts: $run_dir"
echo ""

check_health() {
  local name="$1"
  local url="$2"
  local target_file="$run_dir/${name}_health.json"

  if curl -fsS -m "$TIMEOUT_SECONDS" "$url" >"$target_file" 2>"$run_dir/${name}_health.err"; then
    pass "Health check OK for ${name} (${url})"
  else
    fail "Health check failed for ${name} (${url})"
  fi
}

check_health "gateway" "${GATEWAY_URL%/}/health"
check_health "api" "${API_URL%/}/health"
check_health "qdrant" "http://localhost:6333/health"

echo ""
echo "Triggering controlled RBAC deny case..."
deny_payload='{"server_id":"mcp-filesystem","tool_name":"write_file","arguments":{"path":"/workspace/pilot_incident_should_not_write.txt","content":"forbidden write for analyst role"}}'
deny_code="$(
  curl -sS -m "$TIMEOUT_SECONDS" \
    -o "$run_dir/rbac_deny_response.json" \
    -w "%{http_code}" \
    -X POST "${GATEWAY_URL%/}/mcp/tools/call" \
    -H "Authorization: Bearer ${ANALYST_KEY}" \
    -H "Content-Type: application/json" \
    -d "$deny_payload" || true
)"

if [[ "$deny_code" == "403" ]]; then
  pass "Expected deny received for analyst write attempt (HTTP 403)"
else
  fail "Expected HTTP 403 for analyst write attempt, got ${deny_code}"
fi

if [[ "$SKIP_AUDIT" -eq 1 ]]; then
  warn "Audit export skipped by user flag"
else
  echo ""
  echo "Exporting audit evidence..."
  audit_code="$(
    curl -sS -m "$TIMEOUT_SECONDS" \
      -o "$run_dir/audit_export.json" \
      -w "%{http_code}" \
      "${API_URL%/}/audit?format=json&limit=50&workspace=${WORKSPACE_ID}&type=mcp_tool_call" \
      -H "Authorization: Bearer ${API_KEY}" \
      -H "X-API-Key: ${API_KEY}" || true
  )"

  if [[ "$audit_code" == "200" ]]; then
    pass "Audit export captured (HTTP 200)"
  else
    warn "Audit export not available (HTTP ${audit_code}); check auth/environment"
  fi
fi

{
  echo "pilot_incident_drill_timestamp=${timestamp}"
  echo "gateway_url=${GATEWAY_URL}"
  echo "api_url=${API_URL}"
  echo "workspace_id=${WORKSPACE_ID}"
  echo "passed=${PASSED}"
  echo "warnings=${WARNINGS}"
  echo "failed=${FAILED}"
} > "${run_dir}/summary.txt"

echo ""
echo "=== Drill Summary ==="
echo "Passed:   ${PASSED}"
echo "Warnings: ${WARNINGS}"
echo "Failed:   ${FAILED}"
echo "Artifacts: ${run_dir}"

if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi

exit 0
