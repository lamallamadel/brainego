#!/bin/bash
# Backup System Setup Script
# Initializes backup infrastructure

set -e

echo "========================================="
echo "Backup System Setup"
echo "========================================="
echo ""

# Step 1: Create backup directories
echo "Creating backup directories..."
mkdir -p backups
mkdir -p incident_reports
mkdir -p validation_reports

# Step 2: Set permissions
echo "Setting permissions..."
chmod +x backup_manual.sh
chmod +x restore_manual.sh
chmod +x backup_setup.sh

# Step 3: Install Python dependencies
echo "Installing Python dependencies..."
if command -v pip &> /dev/null; then
    pip install -q boto3 apscheduler qdrant-client neo4j psycopg2-binary
    echo "Dependencies installed"
else
    echo "Warning: pip not found. Please install manually:"
    echo "  pip install boto3 apscheduler qdrant-client neo4j psycopg2-binary"
fi

# Step 4: Initialize MinIO bucket
echo ""
echo "Initializing MinIO bucket..."
docker compose up -d minio
sleep 5

# Wait for MinIO to be ready
echo "Waiting for MinIO to be ready..."
until curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo " Ready!"

# Create backup bucket using Python
python3 << 'EOF'
import boto3
from botocore.exceptions import ClientError

s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin123'
)

try:
    s3_client.head_bucket(Bucket='backups')
    print("Backup bucket 'backups' already exists")
except ClientError:
    s3_client.create_bucket(Bucket='backups')
    print("Created backup bucket 'backups'")
EOF

# Step 5: Create PostgreSQL backup history table
echo ""
echo "Creating backup history table..."
docker compose up -d postgres
sleep 5

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until docker exec postgres pg_isready -U ai_user -d ai_platform > /dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo " Ready!"

docker exec postgres psql -U ai_user -d ai_platform << 'EOSQL'
CREATE TABLE IF NOT EXISTS backup_history (
    id SERIAL PRIMARY KEY,
    backup_id VARCHAR(255) NOT NULL,
    backup_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    size_bytes BIGINT,
    checksum VARCHAR(64),
    status VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_backup_history_timestamp ON backup_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_backup_history_type ON backup_history(backup_type);
CREATE INDEX IF NOT EXISTS idx_backup_history_status ON backup_history(status);

SELECT 'Backup history table created successfully' AS status;
EOSQL

# Step 6: Test backup service
echo ""
echo "Testing backup service..."
echo "Running test backup..."
python backup_service.py --run-once || true

# Step 7: Setup complete
echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Backup system is ready. You can now:"
echo ""
echo "1. Run manual backup:"
echo "   ./backup_manual.sh"
echo ""
echo "2. List available backups:"
echo "   python restore_backup.py --list"
echo ""
echo "3. Test restore (validation only):"
echo "   python restore_backup.py --validate-only --type all"
echo ""
echo "4. Run integrity validation:"
echo "   python validate_data_integrity.py"
echo ""
echo "5. Start automated backup service:"
echo "   docker compose up -d backup-service"
echo ""
echo "For disaster recovery procedures, see:"
echo "   DISASTER_RECOVERY_RUNBOOK.md"
echo ""
