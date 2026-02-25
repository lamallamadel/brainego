#!/bin/bash
# Rollback Migration Script
# Restores Docker Compose environment after failed Kubernetes migration

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

NAMESPACE="${NAMESPACE:-ai-platform}"
WORK_DIR="${WORK_DIR:-./migration_work}"

echo -e "${BLUE}======================================"
echo "Migration Rollback Script"
echo -e "======================================${NC}"
echo ""

confirm_rollback() {
    echo -e "${YELLOW}WARNING: This will scale down Kubernetes deployments${NC}"
    echo "and restore Docker Compose environment."
    echo ""
    read -p "Are you sure you want to rollback? (yes/no): " -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "Rollback cancelled."
        exit 1
    fi
}

scale_down_k8s() {
    echo "Step 1: Scaling Down Kubernetes Resources"
    echo "==========================================="
    
    echo "Scaling down deployments..."
    if kubectl get deployments -n "$NAMESPACE" &>/dev/null; then
        kubectl scale deployment --all --replicas=0 -n "$NAMESPACE" 2>/dev/null || true
        echo -e "${GREEN}✓${NC} Deployments scaled down"
    fi
    
    echo "Scaling down statefulsets..."
    if kubectl get statefulsets -n "$NAMESPACE" &>/dev/null; then
        kubectl scale statefulset --all --replicas=0 -n "$NAMESPACE" 2>/dev/null || true
        echo -e "${GREEN}✓${NC} StatefulSets scaled down"
    fi
    
    echo ""
    echo "Waiting for pods to terminate..."
    sleep 10
    
    remaining=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l || echo "0")
    echo "Remaining pods: $remaining"
}

verify_docker_volumes() {
    echo ""
    echo "Step 2: Verifying Docker Volumes"
    echo "=================================="
    
    volumes=(
        "postgres-data"
        "qdrant-storage"
        "redis-data"
        "minio-data"
        "neo4j-data"
        "neo4j-logs"
        "jaeger-data"
        "prometheus-data"
        "grafana-data"
    )
    
    missing_volumes=()
    for volume in "${volumes[@]}"; do
        echo -n "Checking ${volume}... "
        if docker volume inspect "$volume" &>/dev/null; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${RED}MISSING${NC}"
            missing_volumes+=("$volume")
        fi
    done
    
    if [ ${#missing_volumes[@]} -gt 0 ]; then
        echo ""
        echo -e "${RED}Warning: Missing volumes detected${NC}"
        echo "The following volumes need to be restored:"
        for vol in "${missing_volumes[@]}"; do
            echo "  - $vol"
        done
        echo ""
        return 1
    fi
    
    return 0
}

restore_volumes() {
    echo ""
    echo "Step 3: Restoring Volumes from Backup"
    echo "======================================="
    
    if [ ! -d "$WORK_DIR/exports" ]; then
        echo -e "${RED}Error: Export directory not found at $WORK_DIR/exports${NC}"
        echo "Cannot restore volumes without backups."
        return 1
    fi
    
    for volume in postgres-data qdrant-storage redis-data minio-data neo4j-data neo4j-logs jaeger-data prometheus-data grafana-data; do
        archive="$WORK_DIR/exports/${volume}.tar.gz"
        
        if [ ! -f "$archive" ]; then
            echo "Skipping ${volume} (no archive found)"
            continue
        fi
        
        echo "Restoring ${volume}..."
        
        # Create volume if it doesn't exist
        if ! docker volume inspect "$volume" &>/dev/null; then
            docker volume create "$volume"
        fi
        
        # Restore from archive
        docker run --rm \
            -v "${volume}:/restore" \
            -v "${WORK_DIR}/exports:/backup" \
            alpine:latest \
            sh -c "cd /restore && rm -rf * && tar xzf /backup/${volume}.tar.gz"
        
        echo -e "${GREEN}✓${NC} Restored ${volume}"
    done
    
    echo ""
    echo -e "${GREEN}Volume restoration complete${NC}"
}

restore_compose_config() {
    echo ""
    echo "Step 4: Restoring Docker Compose Configuration"
    echo "================================================"
    
    if [ -f "$WORK_DIR/backups/docker-compose.yaml" ]; then
        echo "Restoring docker-compose.yaml..."
        cp "$WORK_DIR/backups/docker-compose.yaml" ./docker-compose.yaml
        echo -e "${GREEN}✓${NC} Configuration restored"
    else
        echo -e "${YELLOW}Warning: Backup configuration not found${NC}"
        echo "Using existing docker-compose.yaml"
    fi
}

start_docker_compose() {
    echo ""
    echo "Step 5: Starting Docker Compose Services"
    echo "=========================================="
    
    if [ ! -f "docker-compose.yaml" ]; then
        echo -e "${RED}Error: docker-compose.yaml not found${NC}"
        return 1
    fi
    
    echo "Starting services..."
    docker compose up -d
    
    echo ""
    echo "Waiting for services to start..."
    sleep 15
    
    echo ""
    echo "Service Status:"
    docker compose ps
}

verify_services() {
    echo ""
    echo "Step 6: Verifying Services"
    echo "==========================="
    
    echo -n "Checking API server... "
    if curl -sf http://localhost:8000/health &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARNING${NC} - Service may still be starting"
    fi
    
    echo -n "Checking PostgreSQL... "
    if docker exec postgres pg_isready -U ai_user &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARNING${NC} - Database may still be starting"
    fi
    
    echo -n "Checking Redis... "
    if docker exec redis redis-cli PING &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARNING${NC} - Redis may still be starting"
    fi
}

generate_rollback_report() {
    echo ""
    echo -e "${BLUE}======================================"
    echo "Rollback Summary"
    echo -e "======================================${NC}"
    
    echo "Kubernetes resources scaled down: Yes"
    echo "Docker volumes verified: $(verify_docker_volumes &>/dev/null && echo "Yes" || echo "No")"
    echo "Docker Compose services: $(docker compose ps --format json 2>/dev/null | jq -r '.State' | grep -c "running" || echo "0") running"
    echo ""
    echo "Next steps:"
    echo "1. Verify all services are healthy:"
    echo "   $ docker compose ps"
    echo ""
    echo "2. Check service logs if needed:"
    echo "   $ docker compose logs -f"
    echo ""
    echo "3. Test the API:"
    echo "   $ curl http://localhost:8000/health"
    echo ""
    echo "4. If everything works, you can clean up migration artifacts:"
    echo "   $ rm -rf $WORK_DIR"
    echo ""
}

# Main rollback procedure
confirm_rollback

scale_down_k8s

if verify_docker_volumes; then
    echo -e "${GREEN}All Docker volumes are present${NC}"
else
    echo ""
    read -p "Attempt to restore volumes from backup? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        restore_volumes
    else
        echo -e "${RED}Cannot proceed without volumes${NC}"
        exit 1
    fi
fi

restore_compose_config
start_docker_compose
verify_services
generate_rollback_report

echo -e "${GREEN}Rollback completed!${NC}"
