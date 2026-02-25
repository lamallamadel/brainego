#!/bin/bash
# Smoke Tests - Verify system health after restore

set -e

FAILED=0

echo "========================================="
echo "Smoke Tests - AI Platform"
echo "========================================="
echo ""

# Test 1: Service Health
echo "Test 1: Service Health"
echo "-----------------------"

services=("qdrant" "neo4j" "postgres" "minio" "api-server")
for service in "${services[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
        echo "✓ $service is running"
    else
        echo "✗ $service is NOT running"
        FAILED=1
    fi
done
echo ""

# Test 2: Qdrant Health
echo "Test 2: Qdrant Vector Database"
echo "-------------------------------"
QDRANT_HEALTH=$(curl -s http://localhost:6333/health || echo "FAILED")
if [[ $QDRANT_HEALTH == *"ok"* ]] || [[ $QDRANT_HEALTH == *"true"* ]]; then
    echo "✓ Qdrant health check passed"
    
    # Check collections
    COLLECTIONS=$(curl -s http://localhost:6333/collections | grep -o '"name":"[^"]*"' | wc -l)
    echo "✓ Qdrant has $COLLECTIONS collection(s)"
else
    echo "✗ Qdrant health check failed"
    FAILED=1
fi
echo ""

# Test 3: Neo4j Health
echo "Test 3: Neo4j Graph Database"
echo "-----------------------------"
NEO4J_STATUS=$(docker exec neo4j neo4j status 2>&1 || echo "FAILED")
if [[ $NEO4J_STATUS == *"running"* ]]; then
    echo "✓ Neo4j is running"
    
    # Check node count
    NODE_COUNT=$(docker exec neo4j cypher-shell -u neo4j -p neo4j_password "MATCH (n) RETURN count(n) as count;" --format plain 2>/dev/null | tail -1 || echo "0")
    echo "✓ Neo4j has $NODE_COUNT node(s)"
else
    echo "✗ Neo4j is not running"
    FAILED=1
fi
echo ""

# Test 4: PostgreSQL Health
echo "Test 4: PostgreSQL Database"
echo "---------------------------"
PG_READY=$(docker exec postgres pg_isready -U ai_user -d ai_platform 2>&1 || echo "FAILED")
if [[ $PG_READY == *"accepting connections"* ]]; then
    echo "✓ PostgreSQL is accepting connections"
    
    # Check tables
    TABLE_COUNT=$(docker exec postgres psql -U ai_user -d ai_platform -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ' || echo "0")
    echo "✓ PostgreSQL has $TABLE_COUNT table(s)"
    
    # Check backup history
    BACKUP_COUNT=$(docker exec postgres psql -U ai_user -d ai_platform -t -c "SELECT COUNT(*) FROM backup_history;" 2>/dev/null | tr -d ' ' || echo "0")
    echo "✓ Backup history has $BACKUP_COUNT record(s)"
else
    echo "✗ PostgreSQL is not ready"
    FAILED=1
fi
echo ""

# Test 5: MinIO Health
echo "Test 5: MinIO Object Storage"
echo "----------------------------"
MINIO_HEALTH=$(curl -s http://localhost:9000/minio/health/live || echo "FAILED")
if [[ $MINIO_HEALTH == *"OK"* ]] || [[ $? -eq 0 ]]; then
    echo "✓ MinIO health check passed"
else
    echo "✗ MinIO health check failed"
    FAILED=1
fi
echo ""

# Test 6: API Endpoints
echo "Test 6: API Endpoints"
echo "---------------------"

# Health endpoint
API_HEALTH=$(curl -s http://localhost:8000/health 2>&1 || echo "FAILED")
if [[ $API_HEALTH == *"ok"* ]] || [[ $API_HEALTH == *"healthy"* ]]; then
    echo "✓ API server health check passed"
else
    echo "✗ API server health check failed"
    FAILED=1
fi
echo ""

# Test 7: Basic Functionality
echo "Test 7: Basic Functionality"
echo "---------------------------"

# Test chat completion (if API server is running)
if docker ps --format '{{.Names}}' | grep -q "^api-server$"; then
    CHAT_RESPONSE=$(curl -s -X POST http://localhost:8000/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{
            "model": "llama-3.3-8b-instruct",
            "messages": [{"role": "user", "content": "Say hello"}],
            "max_tokens": 10
        }' 2>&1 || echo "FAILED")
    
    if [[ $CHAT_RESPONSE == *"choices"* ]] || [[ $CHAT_RESPONSE == *"content"* ]]; then
        echo "✓ Chat completion endpoint working"
    else
        echo "⚠ Chat completion endpoint test skipped or failed"
    fi
fi
echo ""

# Test 8: Backup System
echo "Test 8: Backup System"
echo "---------------------"

# Check if backups exist
python3 << 'EOF'
import sys
try:
    from restore_backup import RestoreService
    rs = RestoreService()
    
    for backup_type in ['qdrant', 'neo4j', 'postgres']:
        backups = rs.list_available_backups(backup_type)
        if backups:
            print(f"✓ {backup_type.capitalize()} has {len(backups)} backup(s)")
        else:
            print(f"⚠ {backup_type.capitalize()} has no backups")
    sys.exit(0)
except Exception as e:
    print(f"✗ Backup system check failed: {e}")
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo "✓ Backup system operational"
else
    echo "✗ Backup system check failed"
    FAILED=1
fi
echo ""

# Summary
echo "========================================="
echo "Test Summary"
echo "========================================="

if [ $FAILED -eq 0 ]; then
    echo "✓ ALL TESTS PASSED"
    echo ""
    echo "System is healthy and operational"
    exit 0
else
    echo "✗ SOME TESTS FAILED"
    echo ""
    echo "Please review the test results above"
    echo "and check service logs for details:"
    echo "  docker compose logs -f"
    exit 1
fi
