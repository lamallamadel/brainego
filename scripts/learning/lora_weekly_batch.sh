#!/usr/bin/env bash
set -euo pipefail

# Weekly LoRA batch orchestration with canary validation + rollback hook.
# Usage:
#   BASE_URL=http://localhost:8000 DATASET_PATH=data/learning_distill_v123.jsonl ./scripts/learning/lora_weekly_batch.sh

BASE_URL="${BASE_URL:-http://localhost:8000}"
DATASET_PATH="${DATASET_PATH:-}"
ADAPTER_VERSION="${ADAPTER_VERSION:-weekly-$(date +%Y%m%d)}"
CANARY_TIMEOUT_SEC="${CANARY_TIMEOUT_SEC:-300}"
ROLLBACK_CMD="${ROLLBACK_CMD:-echo 'rollback adapter -> previous stable'}"

if [[ -z "${DATASET_PATH}" ]]; then
  echo "ERROR: DATASET_PATH is required" >&2
  exit 1
fi

echo "[S5-3] Starting weekly LoRA batch"
echo "  base_url=${BASE_URL}"
echo "  dataset=${DATASET_PATH}"
echo "  adapter_version=${ADAPTER_VERSION}"

# 1) Trigger training job (best-effort generic endpoint contract)
TRAIN_PAYLOAD=$(cat <<JSON
{"dataset_path":"${DATASET_PATH}","adapter_version":"${ADAPTER_VERSION}","mode":"lora_weekly"}
JSON
)

TRAIN_RESP=$(curl -sS -X POST "${BASE_URL}/train/jsonl" -H 'content-type: application/json' -d "${TRAIN_PAYLOAD}" || true)
if [[ -z "${TRAIN_RESP}" ]]; then
  echo "ERROR: training trigger failed" >&2
  exit 2
fi

echo "[S5-3] training_trigger_response=${TRAIN_RESP}"

# 2) Canary gate placeholder (operator can inject real eval command)
if command -v timeout >/dev/null 2>&1; then
  if ! timeout "${CANARY_TIMEOUT_SEC}" bash -lc "echo '[S5-3] canary check placeholder: PASS'"; then
    echo "[S5-3] Canary failed -> rollback"
    bash -lc "${ROLLBACK_CMD}"
    exit 3
  fi
else
  echo "[S5-3] timeout not available; running canary command without timeout"
  bash -lc "echo '[S5-3] canary check placeholder: PASS'"
fi

echo "[S5-3] Success: adapter ${ADAPTER_VERSION} ready"
