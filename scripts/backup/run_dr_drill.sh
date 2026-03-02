#!/bin/bash
# Disaster Recovery Drill Runner
# Executes DR drill with proper environment setup and reporting

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Disaster Recovery Drill"
echo "========================================"
echo ""

# Check for required dependencies
echo "Checking dependencies..."

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    exit 1
fi

if ! python3 -c "import boto3" 2>/dev/null; then
    echo -e "${YELLOW}Warning: boto3 not installed - installing...${NC}"
    pip install boto3 botocore
fi

if ! python3 -c "import psycopg2" 2>/dev/null; then
    echo -e "${YELLOW}Warning: psycopg2 not installed - installing...${NC}"
    pip install psycopg2-binary
fi

if ! python3 -c "import httpx" 2>/dev/null; then
    echo -e "${YELLOW}Warning: httpx not installed - installing...${NC}"
    pip install httpx
fi

if ! python3 -c "import qdrant_client" 2>/dev/null; then
    echo -e "${YELLOW}Warning: qdrant-client not installed - installing...${NC}"
    pip install qdrant-client
fi

echo -e "${GREEN}✓ Dependencies OK${NC}"
echo ""

# Load environment variables if .env file exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Loading environment from .env file..."
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Check for MinIO/S3 configuration
if [ -z "$MINIO_ENDPOINT" ]; then
    echo -e "${YELLOW}Warning: MINIO_ENDPOINT not set, using default: minio:9000${NC}"
    export MINIO_ENDPOINT="minio:9000"
fi

if [ -z "$BACKUP_BUCKET" ]; then
    echo -e "${YELLOW}Warning: BACKUP_BUCKET not set, using default: backups${NC}"
    export BACKUP_BUCKET="backups"
fi

echo "MinIO Configuration:"
echo "  Endpoint: $MINIO_ENDPOINT"
echo "  Bucket: $BACKUP_BUCKET"
echo ""

# Parse command line arguments
NEW_CLUSTER_CONFIG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            NEW_CLUSTER_CONFIG="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --config FILE    Path to new cluster configuration JSON file"
            echo "  --help           Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  MINIO_ENDPOINT          MinIO/S3 endpoint (default: minio:9000)"
            echo "  MINIO_ACCESS_KEY        MinIO access key (default: minioadmin)"
            echo "  MINIO_SECRET_KEY        MinIO secret key (default: minioadmin123)"
            echo "  BACKUP_BUCKET           Backup bucket name (default: backups)"
            echo "  DR_POSTGRES_HOST        DR cluster PostgreSQL host"
            echo "  DR_QDRANT_HOST          DR cluster Qdrant host"
            echo "  DR_NEO4J_HOST           DR cluster Neo4j host"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Confirm before proceeding
echo -e "${YELLOW}WARNING: This will perform a disaster recovery drill.${NC}"
echo -e "${YELLOW}This operation will restore backups to the specified cluster.${NC}"
echo ""

if [ -n "$NEW_CLUSTER_CONFIG" ]; then
    echo "New cluster config: $NEW_CLUSTER_CONFIG"
    if [ ! -f "$NEW_CLUSTER_CONFIG" ]; then
        echo -e "${RED}Error: Config file not found: $NEW_CLUSTER_CONFIG${NC}"
        exit 1
    fi
    echo ""
    echo "Configuration preview:"
    cat "$NEW_CLUSTER_CONFIG" | python3 -m json.tool
    echo ""
fi

read -p "Continue with DR drill? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "DR drill cancelled."
    exit 0
fi

# Run the DR drill
echo ""
echo "========================================"
echo "Starting DR Drill..."
echo "========================================"
echo ""

START_TIME=$(date +%s)

if [ -n "$NEW_CLUSTER_CONFIG" ]; then
    python3 "$SCRIPT_DIR/dr_drill.py" --new-cluster-config "$NEW_CLUSTER_CONFIG"
else
    python3 "$SCRIPT_DIR/dr_drill.py"
fi

DRILL_EXIT_CODE=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "========================================"
echo "DR Drill Complete"
echo "========================================"
echo "Duration: ${DURATION}s"
echo ""

# Find the latest report
LATEST_REPORT=$(ls -t dr_drill_report_*.json 2>/dev/null | head -n1)

if [ -n "$LATEST_REPORT" ]; then
    echo "Report saved to: $LATEST_REPORT"
    echo ""
    
    # Extract key metrics from report
    RTO_MET=$(python3 -c "import json; print(json.load(open('$LATEST_REPORT'))['rto_met'])")
    DATA_INTEGRITY=$(python3 -c "import json; print(json.load(open('$LATEST_REPORT'))['data_integrity_verified'])")
    GAPS_COUNT=$(python3 -c "import json; print(len(json.load(open('$LATEST_REPORT'))['identified_gaps']))")
    
    echo "Key Metrics:"
    if [ "$RTO_MET" = "True" ]; then
        echo -e "  RTO Met: ${GREEN}✓ YES${NC}"
    else
        echo -e "  RTO Met: ${RED}✗ NO${NC}"
    fi
    
    if [ "$DATA_INTEGRITY" = "True" ]; then
        echo -e "  Data Integrity: ${GREEN}✓ VERIFIED${NC}"
    else
        echo -e "  Data Integrity: ${RED}✗ ISSUES DETECTED${NC}"
    fi
    
    if [ "$GAPS_COUNT" -eq 0 ]; then
        echo -e "  Identified Gaps: ${GREEN}✓ NONE${NC}"
    else
        echo -e "  Identified Gaps: ${YELLOW}⚠ $GAPS_COUNT${NC}"
    fi
    
    echo ""
    
    # Show recommendations if any
    RECOMMENDATIONS=$(python3 -c "import json; recs = json.load(open('$LATEST_REPORT'))['recommendations']; print('\\n'.join(recs[:3]) if recs else 'None')")
    if [ "$RECOMMENDATIONS" != "None" ]; then
        echo "Top Recommendations:"
        echo "$RECOMMENDATIONS" | while IFS= read -r line; do
            echo "  • $line"
        done
        echo ""
    fi
fi

if [ $DRILL_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ DR drill passed successfully${NC}"
else
    echo -e "${RED}✗ DR drill failed${NC}"
fi

exit $DRILL_EXIT_CODE
