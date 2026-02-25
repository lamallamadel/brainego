#!/bin/bash
# Pre-flight Check Script for Kubernetes Migration
# Verifies all prerequisites before starting migration

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

NAMESPACE="${NAMESPACE:-ai-platform}"
MIN_DISK_SPACE_GB=810  # 3x 270GB for working space
REQUIRED_VOLUMES=(
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

echo -e "${BLUE}======================================"
echo "Kubernetes Migration Pre-flight Check"
echo -e "======================================${NC}"
echo ""

CHECKS_PASSED=0
CHECKS_FAILED=0

check_command() {
    local cmd=$1
    local name=$2
    
    echo -n "Checking ${name}... "
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | head -n1 || echo "unknown")
        echo -e "${GREEN}OK${NC} ($version)"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}FAILED${NC} - ${cmd} not found"
        ((CHECKS_FAILED++))
        return 1
    fi
}

check_docker() {
    echo -n "Checking Docker daemon... "
    if docker info &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}FAILED${NC} - Docker daemon not accessible"
        ((CHECKS_FAILED++))
        return 1
    fi
}

check_kubectl() {
    echo -n "Checking kubectl connection... "
    if kubectl cluster-info &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${RED}FAILED${NC} - Cannot connect to Kubernetes cluster"
        ((CHECKS_FAILED++))
        return 1
    fi
}

check_namespace() {
    echo -n "Checking namespace ${NAMESPACE}... "
    if kubectl get namespace "$NAMESPACE" &>/dev/null; then
        echo -e "${GREEN}OK${NC} (exists)"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${YELLOW}WARNING${NC} - Will be created"
        echo "  Run: kubectl create namespace ${NAMESPACE}"
        ((CHECKS_PASSED++))
        return 0
    fi
}

check_docker_volumes() {
    echo ""
    echo "Checking Docker Volumes"
    echo "-----------------------"
    
    local missing=0
    for volume in "${REQUIRED_VOLUMES[@]}"; do
        echo -n "  ${volume}... "
        if docker volume inspect "$volume" &>/dev/null; then
            size=$(docker volume inspect "$volume" --format '{{.Mountpoint}}' | xargs -I {} du -sh {} 2>/dev/null | cut -f1 || echo "unknown")
            echo -e "${GREEN}OK${NC} ($size)"
            ((CHECKS_PASSED++))
        else
            echo -e "${YELLOW}NOT FOUND${NC}"
            ((missing++))
        fi
    done
    
    if [ $missing -gt 0 ]; then
        echo -e "${YELLOW}Warning: $missing volumes not found. They may not have been created yet.${NC}"
    fi
}

check_disk_space() {
    echo ""
    echo "Checking Disk Space"
    echo "-------------------"
    
    available_space=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
    echo "  Available space: ${available_space}GB"
    echo "  Required space: ${MIN_DISK_SPACE_GB}GB"
    
    if [ "$available_space" -ge "$MIN_DISK_SPACE_GB" ]; then
        echo -e "  ${GREEN}OK${NC} - Sufficient disk space"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "  ${RED}FAILED${NC} - Insufficient disk space"
        echo "  Please free up at least $((MIN_DISK_SPACE_GB - available_space))GB"
        ((CHECKS_FAILED++))
        return 1
    fi
}

check_storage_class() {
    echo ""
    echo "Checking Storage Class"
    echo "----------------------"
    
    echo -n "Checking default storage class... "
    if kubectl get storageclass 2>/dev/null | grep -q "(default)"; then
        default_sc=$(kubectl get storageclass 2>/dev/null | grep "(default)" | awk '{print $1}')
        echo -e "${GREEN}OK${NC} ($default_sc)"
        ((CHECKS_PASSED++))
        return 0
    else
        echo -e "${YELLOW}WARNING${NC} - No default storage class found"
        echo "  Available storage classes:"
        kubectl get storageclass 2>/dev/null | tail -n +2 | awk '{print "    - " $1}'
        echo "  You may need to specify storageClassName in PVCs"
        return 0
    fi
}

check_python() {
    echo ""
    echo "Checking Python Environment"
    echo "---------------------------"
    
    echo -n "Checking Python version... "
    if command -v python3 &>/dev/null; then
        py_version=$(python3 --version 2>&1)
        echo -e "${GREEN}OK${NC} ($py_version)"
        ((CHECKS_PASSED++))
    else
        echo -e "${RED}FAILED${NC} - Python 3 not found"
        ((CHECKS_FAILED++))
        return 1
    fi
    
    echo -n "Checking PyYAML... "
    if python3 -c "import yaml" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        ((CHECKS_PASSED++))
    else
        echo -e "${YELLOW}WARNING${NC} - PyYAML not installed"
        echo "  Install with: pip install pyyaml"
        ((CHECKS_FAILED++))
    fi
}

check_docker_compose_running() {
    echo ""
    echo "Checking Docker Compose Services"
    echo "---------------------------------"
    
    echo -n "Checking if services are running... "
    if [ -f "docker-compose.yaml" ]; then
        running=$(docker compose ps --format json 2>/dev/null | jq -r '.State' 2>/dev/null | grep -c "running" || echo "0")
        if [ "$running" -gt 0 ]; then
            echo -e "${YELLOW}WARNING${NC} - $running services running"
            echo "  For data consistency, stop services before migration:"
            echo "  $ docker compose down"
            echo ""
            echo "  Running services:"
            docker compose ps --format "table {{.Name}}\t{{.State}}" 2>/dev/null | grep "running" | sed 's/^/    /'
        else
            echo -e "${GREEN}OK${NC} - No services running"
            ((CHECKS_PASSED++))
        fi
    else
        echo -e "${YELLOW}WARNING${NC} - docker-compose.yaml not found"
    fi
}

estimate_migration_time() {
    echo ""
    echo "Migration Time Estimate"
    echo "-----------------------"
    
    total_size=0
    for volume in "${REQUIRED_VOLUMES[@]}"; do
        if docker volume inspect "$volume" &>/dev/null; then
            mountpoint=$(docker volume inspect "$volume" --format '{{.Mountpoint}}')
            size_bytes=$(du -sb "$mountpoint" 2>/dev/null | cut -f1 || echo "0")
            total_size=$((total_size + size_bytes))
        fi
    done
    
    total_gb=$((total_size / 1024 / 1024 / 1024))
    
    echo "  Total data size: ~${total_gb}GB"
    
    if [ "$total_gb" -lt 10 ]; then
        echo "  Estimated time: 20-35 minutes"
    elif [ "$total_gb" -lt 50 ]; then
        echo "  Estimated time: 50-100 minutes"
    elif [ "$total_gb" -lt 200 ]; then
        echo "  Estimated time: 100-200 minutes"
    else
        echo "  Estimated time: 3-7 hours"
    fi
}

# Main checks
echo "System Requirements"
echo "==================="
check_command "docker" "Docker"
check_command "kubectl" "kubectl"
check_command "python3" "Python 3"
check_docker
check_kubectl

echo ""
echo "Kubernetes Environment"
echo "======================"
check_namespace
check_storage_class

check_docker_volumes
check_disk_space
check_python
check_docker_compose_running
estimate_migration_time

echo ""
echo -e "${BLUE}======================================"
echo "Pre-flight Check Summary"
echo -e "======================================${NC}"
echo "Checks passed: ${CHECKS_PASSED}"
echo "Checks failed: ${CHECKS_FAILED}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "Ready to start migration:"
    echo "  $ python migrate_to_k8s.py full"
    echo ""
    echo "Or run step by step:"
    echo "  $ python migrate_to_k8s.py export"
    echo "  $ python migrate_to_k8s.py validate"
    echo "  $ python migrate_to_k8s.py import"
    exit 0
else
    echo -e "${RED}✗ Some checks failed${NC}"
    echo ""
    echo "Please fix the issues above before proceeding."
    exit 1
fi
