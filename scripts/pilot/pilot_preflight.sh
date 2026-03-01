#!/usr/bin/env bash
# Pilot readiness preflight checks (AFR-96).

set -euo pipefail

CHECK_HEALTH=0
STRICT_ENV=0

PASSED=0
WARNINGS=0
FAILED=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

usage() {
  cat <<'EOF'
Usage: bash scripts/pilot/pilot_preflight.sh [options]

Options:
  --check-health   Also check runtime HTTP health endpoints
  --strict-env     Treat missing pilot env vars as failures
  -h, --help       Show this help
EOF
}

while (($#)); do
  case "$1" in
    --check-health)
      CHECK_HEALTH=1
      shift
      ;;
    --strict-env)
      STRICT_ENV=1
      shift
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

pass() {
  echo -e "${GREEN}[PASS]${NC} $1"
  PASSED=$((PASSED + 1))
}

warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
  WARNINGS=$((WARNINGS + 1))
}

fail() {
  echo -e "${RED}[FAIL]${NC} $1"
  FAILED=$((FAILED + 1))
}

check_command() {
  local cmd="$1"
  local required="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "Command available: ${cmd}"
  else
    if [[ "$required" == "required" ]]; then
      fail "Missing required command: ${cmd}"
    else
      warn "Missing optional command: ${cmd}"
    fi
  fi
}

check_file() {
  local path="$1"
  if [[ -f "$path" ]]; then
    pass "File present: ${path}"
  else
    fail "Missing required file: ${path}"
  fi
}

check_env_var() {
  local name="$1"
  local required="$2"
  if [[ -n "${!name:-}" ]]; then
    pass "Env set: ${name}"
  else
    if [[ "$required" == "required" ]]; then
      fail "Missing required env: ${name}"
    else
      warn "Missing optional env: ${name}"
    fi
  fi
}

contains_key() {
  local csv="$1"
  local expected="$2"
  local token
  IFS=',' read -r -a tokens <<< "$csv"
  for token in "${tokens[@]}"; do
    if [[ "${token// /}" == "$expected" ]]; then
      return 0
    fi
  done
  return 1
}

check_health() {
  local name="$1"
  local url="$2"
  if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
    pass "Health OK: ${name} (${url})"
  else
    fail "Health check failed: ${name} (${url})"
  fi
}

echo -e "${BLUE}==============================================${NC}"
echo -e "${BLUE} Pilot Preflight (AFR-96)${NC}"
echo -e "${BLUE}==============================================${NC}"
echo ""

echo "1) Command checks"
check_command "python3" "required"
check_command "curl" "required"
check_command "docker" "optional"
check_command "node" "optional"
check_command "npm" "optional"
echo ""

echo "2) Required file checks"
check_file "configs/mcp-servers.yaml"
check_file "configs/mcp-acl.yaml"
check_file "configs/tool-policy.yaml"
check_file "configs/safety-policy.yaml"
check_file "docs/pilot_readiness_runbook.md"
echo ""

echo "3) Environment checks"
if [[ "$STRICT_ENV" -eq 1 ]]; then
  check_env_var "API_KEYS" "required"
  check_env_var "WORKSPACE_IDS" "required"
else
  check_env_var "API_KEYS" "optional"
  check_env_var "WORKSPACE_IDS" "optional"
fi
check_env_var "GITHUB_TOKEN" "optional"
check_env_var "NOTION_API_KEY" "optional"
echo ""

if [[ -n "${API_KEYS:-}" ]]; then
  if contains_key "$API_KEYS" "sk-test-key-123"; then
    pass "API_KEYS contains sk-test-key-123"
  else
    warn "API_KEYS does not include sk-test-key-123"
  fi

  if contains_key "$API_KEYS" "sk-admin-key-456"; then
    pass "API_KEYS contains sk-admin-key-456"
  else
    warn "API_KEYS does not include sk-admin-key-456"
  fi
fi

echo ""
if [[ "$CHECK_HEALTH" -eq 1 ]]; then
  echo "4) Runtime health checks"
  check_health "api-server" "http://localhost:8000/health"
  check_health "mcpjungle-gateway" "http://localhost:9100/health"
  check_health "qdrant" "http://localhost:6333/health"
  echo ""
else
  echo "4) Runtime health checks"
  warn "Skipped (use --check-health to enable)"
  echo ""
fi

echo -e "${BLUE}==============================================${NC}"
echo "Summary:"
echo "  Passed:   ${PASSED}"
echo "  Warnings: ${WARNINGS}"
echo "  Failed:   ${FAILED}"
echo -e "${BLUE}==============================================${NC}"

if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi

exit 0
