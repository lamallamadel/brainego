#!/bin/bash
# Migration Verification Script
# Verifies data integrity after migration to Kubernetes

set -e

NAMESPACE="${NAMESPACE:-ai-platform}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================"
echo "Migration Verification Script"
echo "======================================"
echo ""

check_pvc() {
    local pvc=$1
    echo -n "Checking PVC ${pvc}... "
    
    if kubectl get pvc "$pvc" -n "$NAMESPACE" &>/dev/null; then
        status=$(kubectl get pvc "$pvc" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
        if [ "$status" = "Bound" ]; then
            echo -e "${GREEN}OK${NC} (Bound)"
            return 0
        else
            echo -e "${YELLOW}WARNING${NC} (Status: $status)"
            return 1
        fi
    else
        echo -e "${RED}FAILED${NC} (Not found)"
        return 1
    fi
}

check_pod() {
    local pod=$1
    echo -n "Checking pod ${pod}... "
    
    if kubectl get pod "$pod" -n "$NAMESPACE" &>/dev/null; then
        status=$(kubectl get pod "$pod" -n "$NAMESPACE" -o jsonpath='{.status.phase}')
        if [ "$status" = "Running" ]; then
            echo -e "${GREEN}OK${NC} (Running)"
            return 0
        else
            echo -e "${YELLOW}WARNING${NC} (Status: $status)"
            return 1
        fi
    else
        echo -e "${RED}FAILED${NC} (Not found)"
        return 1
    fi
}

check_postgres() {
    echo ""
    echo "PostgreSQL Data Verification"
    echo "------------------------------"
    
    if ! check_pod "postgres-0"; then
        return 1
    fi
    
    echo "Checking database tables..."
    if kubectl exec -n "$NAMESPACE" postgres-0 -- psql -U ai_user -d ai_platform -c "\dt" &>/dev/null; then
        echo -e "${GREEN}OK${NC} - Database accessible"
        
        tables=$(kubectl exec -n "$NAMESPACE" postgres-0 -- psql -U ai_user -d ai_platform -t -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';")
        echo "  Tables found: $(echo $tables | xargs)"
    else
        echo -e "${RED}FAILED${NC} - Cannot access database"
        return 1
    fi
}

check_qdrant() {
    echo ""
    echo "Qdrant Data Verification"
    echo "-------------------------"
    
    if ! check_pod "qdrant-0"; then
        return 1
    fi
    
    echo "Checking collections..."
    if kubectl exec -n "$NAMESPACE" qdrant-0 -- wget -q -O - http://localhost:6333/collections 2>/dev/null | grep -q "result"; then
        echo -e "${GREEN}OK${NC} - Qdrant accessible"
        
        collections=$(kubectl exec -n "$NAMESPACE" qdrant-0 -- wget -q -O - http://localhost:6333/collections 2>/dev/null)
        echo "  Collections: $collections"
    else
        echo -e "${YELLOW}WARNING${NC} - Cannot fetch collections (may be empty)"
    fi
}

check_redis() {
    echo ""
    echo "Redis Data Verification"
    echo "------------------------"
    
    if ! check_pod "redis-0"; then
        return 1
    fi
    
    echo "Checking Redis data..."
    if kubectl exec -n "$NAMESPACE" redis-0 -- redis-cli PING &>/dev/null; then
        echo -e "${GREEN}OK${NC} - Redis accessible"
        
        dbsize=$(kubectl exec -n "$NAMESPACE" redis-0 -- redis-cli DBSIZE | grep -o '[0-9]*')
        echo "  Keys in database: $dbsize"
    else
        echo -e "${RED}FAILED${NC} - Cannot connect to Redis"
        return 1
    fi
}

check_neo4j() {
    echo ""
    echo "Neo4j Data Verification"
    echo "------------------------"
    
    if ! check_pod "neo4j-0"; then
        return 1
    fi
    
    echo "Checking Neo4j..."
    if kubectl exec -n "$NAMESPACE" neo4j-0 -- cypher-shell -u neo4j -p neo4j_password "MATCH (n) RETURN count(n) LIMIT 1;" &>/dev/null; then
        echo -e "${GREEN}OK${NC} - Neo4j accessible"
    else
        echo -e "${YELLOW}WARNING${NC} - Cannot connect to Neo4j (may need initialization)"
    fi
}

check_minio() {
    echo ""
    echo "MinIO Data Verification"
    echo "------------------------"
    
    if ! check_pod "minio-0"; then
        return 1
    fi
    
    echo "Checking MinIO..."
    if kubectl exec -n "$NAMESPACE" minio-0 -- sh -c "ls -la /data/.minio.sys" &>/dev/null; then
        echo -e "${GREEN}OK${NC} - MinIO data directory exists"
    else
        echo -e "${YELLOW}WARNING${NC} - MinIO system directory not found"
    fi
}

check_prometheus() {
    echo ""
    echo "Prometheus Data Verification"
    echo "-----------------------------"
    
    if ! check_pod "prometheus-0"; then
        return 1
    fi
    
    echo "Checking Prometheus..."
    if kubectl exec -n "$NAMESPACE" prometheus-0 -- sh -c "ls -la /prometheus/wal" &>/dev/null; then
        echo -e "${GREEN}OK${NC} - Prometheus WAL directory exists"
    else
        echo -e "${YELLOW}WARNING${NC} - Prometheus WAL not found"
    fi
}

check_grafana() {
    echo ""
    echo "Grafana Data Verification"
    echo "--------------------------"
    
    if ! check_pod "grafana-0"; then
        return 1
    fi
    
    echo "Checking Grafana..."
    if kubectl exec -n "$NAMESPACE" grafana-0 -- sh -c "ls -la /var/lib/grafana/grafana.db" &>/dev/null; then
        echo -e "${GREEN}OK${NC} - Grafana database exists"
    else
        echo -e "${YELLOW}WARNING${NC} - Grafana database not found"
    fi
}

# Main verification
echo "Step 1: Checking PVCs"
echo "====================="
pvcs=(
    "postgres-data"
    "qdrant-data"
    "redis-data"
    "minio-data"
    "neo4j-data"
    "neo4j-logs"
    "jaeger-data"
    "prometheus-data"
    "grafana-data"
)

pvc_failures=0
for pvc in "${pvcs[@]}"; do
    check_pvc "$pvc" || ((pvc_failures++))
done

echo ""
echo "Step 2: Checking StatefulSet Pods"
echo "==================================="
pods=(
    "postgres-0"
    "qdrant-0"
    "redis-0"
    "minio-0"
    "neo4j-0"
    "prometheus-0"
    "grafana-0"
)

pod_failures=0
for pod in "${pods[@]}"; do
    check_pod "$pod" || ((pod_failures++))
done

echo ""
echo "Step 3: Detailed Data Verification"
echo "===================================="

check_postgres || true
check_qdrant || true
check_redis || true
check_neo4j || true
check_minio || true
check_prometheus || true
check_grafana || true

echo ""
echo "======================================"
echo "Verification Summary"
echo "======================================"
echo "PVC failures: $pvc_failures/${#pvcs[@]}"
echo "Pod failures: $pod_failures/${#pods[@]}"

if [ $pvc_failures -eq 0 ] && [ $pod_failures -eq 0 ]; then
    echo -e "${GREEN}Overall Status: PASSED${NC}"
    exit 0
else
    echo -e "${YELLOW}Overall Status: WARNINGS${NC}"
    exit 1
fi
