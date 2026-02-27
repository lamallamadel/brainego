#!/usr/bin/env bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
  echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

compose() {
  docker compose "${COMPOSE_ARGS[@]}" "$@"
}

wait_for_service() {
  local service="$1"
  local max_wait="${2:-180}"
  local interval="${3:-5}"
  local elapsed=0

  print_info "Waiting for ${service}..."

  while [ "$elapsed" -lt "$max_wait" ]; do
    local status
    status="$(compose ps --status running "$service" --format json 2>/dev/null || true)"

    if echo "$status" | rg -q '"Health":"healthy"|"State":"running"'; then
      print_success "${service} is ready"
      return 0
    fi

    sleep "$interval"
    elapsed=$((elapsed + interval))
  done

  print_warning "${service} did not become ready after ${max_wait}s"
  return 1
}

print_info "==================================="
print_info "AI Platform Initialization Script"
print_info "==================================="

ensure_prerequisites() {
  print_info "Checking Docker installation..."
  if ! command_exists docker; then
    print_error "Docker is not installed."
    exit 1
  fi
  print_success "Docker is installed"

  print_info "Checking Docker Compose availability..."
  if ! docker compose version >/dev/null 2>&1; then
    print_error "Docker Compose v2 (docker compose) is required."
    exit 1
  fi
  print_success "Docker Compose is available"

  print_info "Checking Docker daemon..."
  if ! docker info >/dev/null 2>&1; then
    print_error "Docker daemon is not running."
    exit 1
  fi
  print_success "Docker daemon is running"
}

check_gpu() {
  print_info "Checking GPU with nvidia-smi..."
  if ! command_exists nvidia-smi; then
    print_warning "nvidia-smi not found. GPU workloads may fail."
    return 0
  fi

  if ! nvidia-smi >/dev/null 2>&1; then
    print_warning "nvidia-smi is present but not healthy."
    return 0
  fi

  print_success "nvidia-smi is available"
  nvidia-smi --query-gpu=name --format=csv,noheader | sed 's/^/  - /'

  print_info "Validating GPU runtime in Docker..."
  if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
    print_success "NVIDIA container runtime is configured"
  else
    print_warning "NVIDIA container runtime is not configured."
    print_warning "Install nvidia-container-toolkit for GPU containers."
  fi
}

prepare_dirs() {
  print_info "Preparing directories..."
  mkdir -p models configs init-scripts/postgres logs workspace lora_adapters fisher_matrices
  print_success "Directories prepared"
}

ensure_env_file() {
  if [ -f .env ]; then
    print_info ".env already exists"
    return 0
  fi

  print_info "Creating default .env file..."
  cat > .env <<'ENVEOF'
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
REDIS_MAX_MEMORY=2gb
COMPOSE_PROJECT_NAME=ai-platform
ENVEOF
  print_success "Created .env"
}

setup_compose_args() {
  COMPOSE_ARGS=(-f docker-compose.yaml)

  if [ "${USE_DOCKER_CLOUD_CONFIG:-false}" = "true" ] && [ -f docker-compose.observability.yml ]; then
    COMPOSE_ARGS+=(-f docker-compose.observability.yml)
    print_info "Using compose override: docker-compose.observability.yml"
  fi
}

create_named_volumes() {
  print_info "Ensuring Docker named volumes exist..."

  local project_name
  project_name="$(basename "$(pwd)")"
  if [ -f .env ]; then
    local env_project_name
    env_project_name="$(awk -F= '$1=="COMPOSE_PROJECT_NAME" {print $2}' .env | tail -n 1 | tr -d '[:space:]')"
    if [ -n "${env_project_name}" ]; then
      project_name="$env_project_name"
    fi
  fi

  local volumes=(
    max-models max-configs max-logs qdrant-storage redis-data postgres-data minio-data
    jaeger-data neo4j-data neo4j-logs neo4j-import neo4j-plugins prometheus-data
    grafana-data loki-data alertmanager-data
  )

  for volume in "${volumes[@]}"; do
    local full_name="${project_name}_${volume}"
    if docker volume inspect "$full_name" >/dev/null 2>&1; then
      print_info "Volume exists: $full_name"
      continue
    fi

    docker volume create "$full_name" >/dev/null
    print_success "Created volume: $full_name"
  done
}

pull_images() {
  print_info "Pulling required images..."
  compose pull
  print_success "Images pulled"
}

start_stack_in_order() {
  print_info "Starting data layer..."
  compose up -d redis postgres minio qdrant neo4j jaeger
  wait_for_service redis 90
  wait_for_service postgres 120
  wait_for_service minio 120
  wait_for_service qdrant 120
  wait_for_service neo4j 180 || true

  print_info "Starting observability layer..."
  compose up -d prometheus loki alertmanager otel-collector promtail grafana redis-exporter postgres-exporter nvidia-gpu-exporter

  print_info "Starting model and embedding services..."
  compose up -d max-serve-llama max-serve-qwen max-serve-deepseek embedding-service

  print_info "Starting application services..."
  compose up -d api-server gateway mcpjungle-gateway mem0 learning-engine drift-monitor maml-service data-collection ingestion-worker backup-service

  print_success "Stack started in dependency order"
}

show_summary() {
  print_info "Service status:"
  compose ps

  echo
  print_info "Key endpoints:"
  echo "  - API Server:         http://localhost:8000"
  echo "  - Gateway:            http://localhost:9002"
  echo "  - MCPJungle Gateway:  http://localhost:9100"
  echo "  - Qdrant:             http://localhost:6333"
  echo "  - MinIO Console:      http://localhost:9001"
  echo "  - Grafana:            http://localhost:3000"
  echo "  - Prometheus:         http://localhost:9090"
  echo "  - Jaeger:             http://localhost:16686"

  echo
  print_success "Initialization complete"
}

main() {
  ensure_prerequisites
  check_gpu
  prepare_dirs
  ensure_env_file
  setup_compose_args
  create_named_volumes
  pull_images
  start_stack_in_order
  show_summary
}

main "$@"
