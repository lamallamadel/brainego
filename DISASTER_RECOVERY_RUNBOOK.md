# Disaster Recovery Runbook

## Table of Contents
1. [Overview](#overview)
2. [Backup Architecture](#backup-architecture)
3. [Prerequisites](#prerequisites)
4. [Recovery Procedures](#recovery-procedures)
5. [Validation](#validation)
6. [Rollback Procedures](#rollback-procedures)
7. [Common Scenarios](#common-scenarios)
8. [Troubleshooting](#troubleshooting)
9. [Contact Information](#contact-information)

---

## Overview

This runbook provides step-by-step procedures for recovering from data loss or corruption in the AI Platform. The platform uses automated daily backups of:

- **Qdrant** - Vector database (snapshots via API)
- **Neo4j** - Graph database (neo4j-admin dumps)
- **PostgreSQL** - Relational database (pg_dump custom format)

All backups are stored in **MinIO** (S3-compatible storage) with **30-day retention**.

### Backup Schedule
- **Daily backups**: 2:00 AM UTC
- **Retention**: 30 days
- **Storage**: MinIO bucket `backups`

### Recovery Time Objectives (RTO)
- Qdrant: < 15 minutes
- Neo4j: < 30 minutes
- PostgreSQL: < 20 minutes
- Full system: < 60 minutes

### Recovery Point Objectives (RPO)
- 24 hours (daily backups)

---

## Backup Architecture

### Storage Structure
```
backups/
├── qdrant/
│   └── YYYY/MM/DD/
│       └── qdrant_YYYYMMDD_HHMMSS.snapshot
├── neo4j/
│   └── YYYY/MM/DD/
│       └── neo4j_YYYYMMDD_HHMMSS.dump
└── postgres/
    └── YYYY/MM/DD/
        └── postgres_YYYYMMDD_HHMMSS.dump
```

### Backup Metadata
Each backup includes:
- **backup_id**: Unique identifier
- **timestamp**: ISO 8601 format
- **checksum**: SHA256 hash
- **size_bytes**: File size
- **status**: success/failed

Metadata is stored in PostgreSQL `backup_history` table.

### Components

**Backup Service** (`backup_service.py`):
- Automated backup orchestration
- Snapshot creation and upload
- Retention management
- Metadata tracking

**Restore Service** (`restore_backup.py`):
- Backup listing and selection
- Restore execution
- Validation

**Integrity Validator** (`validate_data_integrity.py`):
- Data consistency checks
- Cross-database validation
- Report generation

---

## Prerequisites

### Required Access
- [ ] SSH/kubectl access to production environment
- [ ] Docker access to database containers
- [ ] MinIO credentials (MINIO_ACCESS_KEY, MINIO_SECRET_KEY)
- [ ] Database credentials (PostgreSQL, Neo4j)

### Required Tools
```bash
# Install Python dependencies
pip install -r requirements.txt

# Verify Docker access
docker ps

# Verify MinIO access
export MINIO_ENDPOINT=minio:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin123
```

### Environment Variables
```bash
# MinIO Configuration
export MINIO_ENDPOINT=minio:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin123
export BACKUP_BUCKET=backups

# Qdrant Configuration
export QDRANT_HOST=qdrant
export QDRANT_PORT=6333

# Neo4j Configuration
export NEO4J_HOST=neo4j
export NEO4J_PORT=7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=neo4j_password

# PostgreSQL Configuration
export POSTGRES_HOST=postgres
export POSTGRES_PORT=5432
export POSTGRES_DB=ai_platform
export POSTGRES_USER=ai_user
export POSTGRES_PASSWORD=ai_password
```

---

## Recovery Procedures

### 1. Assess the Situation

#### Step 1.1: Identify the Problem
```bash
# Check service health
docker compose ps

# Check logs for errors
docker compose logs --tail=100 qdrant
docker compose logs --tail=100 neo4j
docker compose logs --tail=100 postgres

# Run integrity validation
python validate_data_integrity.py
```

#### Step 1.2: Determine Recovery Scope
- **Single database** - Restore only affected database
- **Multiple databases** - Restore all affected databases
- **Full system** - Complete disaster recovery

#### Step 1.3: Create Incident Log
```bash
# Document incident details
echo "Incident: [Description]" > incident_$(date +%Y%m%d_%H%M%S).log
echo "Detected: $(date)" >> incident_*.log
echo "Affected: [Services]" >> incident_*.log
```

---

### 2. Stop Affected Services

**IMPORTANT**: Stop services to prevent data inconsistency during restore.

```bash
# Stop all services
docker compose stop

# OR stop individual services
docker compose stop api-server gateway mcpjungle-gateway
docker compose stop learning-engine drift-monitor
```

---

### 3. List Available Backups

```bash
# List all backups
python restore_backup.py --list

# List specific type
python restore_backup.py --list --type qdrant
python restore_backup.py --list --type neo4j
python restore_backup.py --list --type postgres
```

Expected output:
```
QDRANT Backups:
  qdrant_20250130_020000: 2025-01-30 02:00:00 (245.67 MB)
  qdrant_20250129_020000: 2025-01-29 02:00:00 (244.12 MB)
  ...

NEO4J Backups:
  neo4j_20250130_020000: 2025-01-30 02:00:00 (512.34 MB)
  ...

POSTGRES Backups:
  postgres_20250130_020000: 2025-01-30 02:00:00 (128.45 MB)
  ...
```

---

### 4. Execute Restore

#### Option A: Restore Latest Backups

```bash
# Restore all databases (latest backups)
python restore_backup.py --type all

# Restore specific database
python restore_backup.py --type qdrant
python restore_backup.py --type neo4j
python restore_backup.py --type postgres
```

#### Option B: Restore Specific Backup

```bash
# Use specific backup ID
python restore_backup.py --type qdrant --backup-id qdrant_20250128_020000
python restore_backup.py --type neo4j --backup-id neo4j_20250128_020000
python restore_backup.py --type postgres --backup-id postgres_20250128_020000
```

**Warning**: The restore script includes a 5-second countdown before execution.

---

### 5. Validate Restoration

#### Step 5.1: Run Automated Validation

```bash
# Validate all databases
python restore_backup.py --validate-only --type all

# Validate specific database
python restore_backup.py --validate-only --type qdrant
```

#### Step 5.2: Run Integrity Validation

```bash
# Full integrity check
python validate_data_integrity.py

# Review generated report
cat validation_report_*.txt
```

Expected validation checks:
- ✓ Database connectivity
- ✓ Data counts (vectors, nodes, rows)
- ✓ Schema integrity
- ✓ Cross-database consistency
- ✓ No orphaned records
- ✓ No NULL values in critical fields

---

### 6. Restart Services

```bash
# Start all services
docker compose up -d

# Monitor startup
docker compose logs -f

# Wait for health checks
docker compose ps
```

Verify all services show `healthy` status.

---

### 7. Smoke Testing

#### Test 1: API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Test chat completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b-instruct",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

#### Test 2: RAG Query

```bash
# Test vector search
curl -X POST http://localhost:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test query",
    "top_k": 5
  }'
```

#### Test 3: Graph Query

```bash
# Test Neo4j connectivity
curl -X POST http://localhost:8000/api/graph/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (n) RETURN count(n) as count LIMIT 1"
  }'
```

#### Test 4: Database Queries

```bash
# Test PostgreSQL
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT COUNT(*) FROM feedback;"

# Test Qdrant
curl http://localhost:6333/collections

# Test Neo4j
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "MATCH (n) RETURN count(n);"
```

---

### 8. Document Recovery

```bash
# Update incident log
echo "Recovery completed: $(date)" >> incident_*.log
echo "Backup used: [backup_id]" >> incident_*.log
echo "Validation: PASSED" >> incident_*.log

# Save validation report
cp validation_report_*.txt incident_reports/
```

---

## Validation

### Manual Validation Checklist

#### Qdrant Validation
- [ ] Service is healthy (`http://qdrant:6333/health`)
- [ ] Collections exist and contain vectors
- [ ] Vector counts match expected values
- [ ] Sample search queries return results

#### Neo4j Validation
- [ ] Service is running (`docker exec neo4j neo4j status`)
- [ ] Database is accessible (`cypher-shell` connects)
- [ ] Node and relationship counts are reasonable
- [ ] No excessive orphaned nodes
- [ ] Sample graph queries return results

#### PostgreSQL Validation
- [ ] Service is healthy (`pg_isready`)
- [ ] Database is accessible (`psql` connects)
- [ ] Expected tables exist
- [ ] Row counts are reasonable
- [ ] No NULL values in critical columns
- [ ] Foreign key constraints are valid

#### Cross-Database Validation
- [ ] Data consistency across databases
- [ ] No missing references
- [ ] Application integrations work
- [ ] End-to-end workflows complete

---

## Rollback Procedures

### If Restore Fails

#### Option 1: Retry with Different Backup

```bash
# Try previous day's backup
python restore_backup.py --type all --backup-id [previous_backup_id]
```

#### Option 2: Restore from Older Backup

```bash
# List older backups
python restore_backup.py --list

# Restore specific date
python restore_backup.py --backup-id qdrant_20250125_020000
```

#### Option 3: Manual Recovery

**Qdrant Manual Recovery**:
```bash
# Stop Qdrant
docker compose stop qdrant

# Remove corrupted data
docker compose exec qdrant rm -rf /qdrant/storage/*

# Start Qdrant
docker compose start qdrant

# Re-index from source data (application-specific)
```

**Neo4j Manual Recovery**:
```bash
# Access Neo4j container
docker exec -it neo4j bash

# Manual dump load
neo4j stop
neo4j-admin database load neo4j --from-path=/backups
neo4j start
```

**PostgreSQL Manual Recovery**:
```bash
# Drop and recreate database
docker exec postgres psql -U ai_user -d postgres -c "DROP DATABASE ai_platform;"
docker exec postgres psql -U ai_user -d postgres -c "CREATE DATABASE ai_platform;"

# Manual restore
docker exec postgres pg_restore -U ai_user -d ai_platform /tmp/backup.dump
```

---

## Common Scenarios

### Scenario 1: Qdrant Data Corruption

**Symptoms**:
- Search queries return no results
- Collection is empty
- API errors mentioning Qdrant

**Recovery**:
```bash
# Stop services
docker compose stop api-server gateway

# Restore Qdrant
python restore_backup.py --type qdrant

# Validate
python restore_backup.py --validate-only --type qdrant

# Restart services
docker compose start api-server gateway
```

**Estimated Time**: 15 minutes

---

### Scenario 2: Neo4j Database Loss

**Symptoms**:
- Graph queries fail
- Node counts show zero
- Relationship queries return empty

**Recovery**:
```bash
# Stop services
docker compose stop api-server graph-service

# Restore Neo4j
python restore_backup.py --type neo4j

# Validate
python validate_data_integrity.py

# Restart services
docker compose start api-server graph-service
```

**Estimated Time**: 30 minutes

---

### Scenario 3: PostgreSQL Data Loss

**Symptoms**:
- Application errors about missing data
- Empty tables
- Foreign key violations

**Recovery**:
```bash
# Stop all services
docker compose stop

# Restore PostgreSQL
python restore_backup.py --type postgres

# Validate
python restore_backup.py --validate-only --type postgres

# Restart all services
docker compose up -d
```

**Estimated Time**: 20 minutes

---

### Scenario 4: Complete System Failure

**Symptoms**:
- Multiple database failures
- Data center outage
- Hardware failure

**Recovery**:
```bash
# Full system restore
python restore_backup.py --type all

# Full validation
python validate_data_integrity.py

# Restart everything
docker compose down
docker compose up -d

# Run smoke tests
./smoke_tests.sh
```

**Estimated Time**: 60 minutes

---

### Scenario 5: Accidental Data Deletion

**Problem**: User accidentally deleted critical data

**Recovery**:
```bash
# Identify when data existed
python restore_backup.py --list --type postgres

# Restore from before deletion
python restore_backup.py --type postgres --backup-id postgres_YYYYMMDD_020000

# Extract specific data (if partial restore needed)
docker exec postgres pg_restore -U ai_user -d ai_platform -t specific_table /tmp/backup.dump
```

---

### Scenario 6: Backup Service Failure

**Problem**: Daily backups are not running

**Diagnosis**:
```bash
# Check backup service logs
docker compose logs backup-service

# Check last backup
python restore_backup.py --list

# Check MinIO connectivity
curl http://minio:9000/minio/health/live
```

**Recovery**:
```bash
# Run manual backup
python backup_service.py --run-once

# Restart backup service
docker compose restart backup-service

# Verify next scheduled run
docker compose logs -f backup-service
```

---

## Troubleshooting

### Problem: Restore Script Hangs

**Cause**: Large backup file or network timeout

**Solution**:
```bash
# Increase timeout
export HTTPX_TIMEOUT=600

# For PostgreSQL, restore in chunks
docker exec postgres pg_restore -U ai_user -d ai_platform -j 4 /tmp/backup.dump
```

---

### Problem: Checksum Mismatch

**Cause**: Corrupted backup file

**Solution**:
```bash
# Use different backup
python restore_backup.py --list

# Restore from previous day
python restore_backup.py --backup-id [previous_backup]

# If all backups corrupted, check MinIO
docker compose logs minio
```

---

### Problem: Out of Disk Space

**Cause**: Insufficient space for restore

**Solution**:
```bash
# Check disk space
df -h

# Clean up old logs
docker compose exec postgres find /var/log -name "*.log" -mtime +7 -delete

# Clean Docker
docker system prune -a

# Increase volume size (cloud provider)
```

---

### Problem: Neo4j Won't Start After Restore

**Cause**: Database lock or corrupted files

**Solution**:
```bash
# Remove lock files
docker exec neo4j rm -f /data/databases/neo4j/store_lock

# Check database integrity
docker exec neo4j neo4j-admin check-consistency --database=neo4j

# Force rebuild indexes
docker exec neo4j cypher-shell -u neo4j -p neo4j_password "CALL db.indexes()"
```

---

### Problem: Qdrant Collection Not Found

**Cause**: Collection not restored or wrong snapshot

**Solution**:
```bash
# List collections
curl http://localhost:6333/collections

# Recreate collection
curl -X PUT http://localhost:6333/collections/documents \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 384,
      "distance": "Cosine"
    }
  }'

# Restore from different snapshot
python restore_backup.py --type qdrant --backup-id [different_backup]
```

---

### Problem: PostgreSQL Foreign Key Violations

**Cause**: Partial restore or data inconsistency

**Solution**:
```bash
# Disable constraints temporarily
docker exec postgres psql -U ai_user -d ai_platform -c "SET session_replication_role = 'replica';"

# Restore again
python restore_backup.py --type postgres

# Re-enable constraints
docker exec postgres psql -U ai_user -d ai_platform -c "SET session_replication_role = 'origin';"

# Verify integrity
docker exec postgres psql -U ai_user -d ai_platform -c "SELECT COUNT(*) FROM pg_constraint WHERE contype = 'f';"
```

---

## Monitoring and Alerts

### Backup Monitoring

```bash
# Check recent backups
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT backup_type, timestamp, status, size_bytes/1024/1024 as size_mb 
  FROM backup_history 
  ORDER BY timestamp DESC 
  LIMIT 10;
"

# Check for failures
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT backup_type, COUNT(*) as failures
  FROM backup_history 
  WHERE status = 'failed' AND timestamp > NOW() - INTERVAL '7 days'
  GROUP BY backup_type;
"
```

### Alert Configuration

Configure alerts in your monitoring system:

- **Backup Failure**: Alert if backup status = 'failed'
- **Missing Backup**: Alert if no backup in 25 hours
- **Large Backup Size**: Alert if backup size increases >50%
- **Restore Duration**: Alert if restore takes >60 minutes
- **Validation Failure**: Alert if integrity validation fails

---

## Testing Disaster Recovery

### Monthly DR Test Procedure

```bash
# 1. Create test environment
docker compose -f docker-compose.test.yaml up -d

# 2. Restore latest backups to test environment
export POSTGRES_HOST=postgres-test
export QDRANT_HOST=qdrant-test
export NEO4J_HOST=neo4j-test
python restore_backup.py --type all

# 3. Validate test environment
python validate_data_integrity.py

# 4. Run smoke tests
./smoke_tests.sh

# 5. Document results
echo "DR Test $(date): PASSED" >> dr_test_log.txt

# 6. Cleanup
docker compose -f docker-compose.test.yaml down -v
```

---

## Contact Information

### Escalation Path

**Level 1 - On-Call Engineer**:
- Run automated recovery procedures
- Execute validation scripts
- Monitor service health

**Level 2 - Database Administrator**:
- Manual database recovery
- Complex restoration scenarios
- Performance optimization

**Level 3 - Platform Architect**:
- Architecture decisions
- Multi-region failover
- Major incidents

### Important Links

- **Backup Dashboard**: http://localhost:3000/d/backups
- **MinIO Console**: http://localhost:9001
- **Grafana Alerts**: http://localhost:3000/alerting
- **Documentation**: ./DISASTER_RECOVERY_RUNBOOK.md

---

## Appendix A: Backup Service Configuration

### Environment Variables

```bash
# Backup schedule (cron format)
BACKUP_SCHEDULE=0 2 * * *  # 2 AM daily

# Retention period (days)
BACKUP_RETENTION_DAYS=30

# MinIO configuration
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
BACKUP_BUCKET=backups

# Database endpoints
QDRANT_HOST=qdrant
QDRANT_PORT=6333
NEO4J_HOST=neo4j
NEO4J_PORT=7687
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

### Manual Backup Trigger

```bash
# Run backup immediately
python backup_service.py --run-once

# Or via Docker
docker compose exec backup-service python backup_service.py --run-once
```

---

## Appendix B: Backup Size Estimates

| Database | Typical Size | Backup Size (Compressed) | Restore Time |
|----------|--------------|--------------------------|--------------|
| Qdrant   | 500 MB       | 250 MB                   | 5-15 min     |
| Neo4j    | 1 GB         | 500 MB                   | 10-30 min    |
| PostgreSQL| 200 MB      | 100 MB                   | 5-20 min     |
| **Total**| **1.7 GB**   | **850 MB**               | **20-60 min**|

*Sizes vary based on data volume and compression ratios*

---

## Appendix C: Automation Scripts

### Automated Health Check

```bash
#!/bin/bash
# health_check.sh

echo "Running health checks..."

# Check Qdrant
curl -f http://localhost:6333/health || echo "Qdrant FAILED"

# Check Neo4j
docker exec neo4j neo4j status || echo "Neo4j FAILED"

# Check PostgreSQL
docker exec postgres pg_isready -U ai_user || echo "PostgreSQL FAILED"

# Check backups
python -c "
from restore_backup import RestoreService
rs = RestoreService()
backups = rs.list_available_backups()
if not backups:
    print('No backups found!')
    exit(1)
print(f'Found {len(backups)} backups')
"
```

### Automated Recovery Test

```bash
#!/bin/bash
# test_recovery.sh

set -e

echo "Testing disaster recovery procedures..."

# Test backup listing
python restore_backup.py --list

# Test validation
python restore_backup.py --validate-only --type all

# Test integrity check
python validate_data_integrity.py

echo "Recovery test completed successfully"
```

---

## Version History

| Version | Date       | Author | Changes                    |
|---------|------------|--------|----------------------------|
| 1.0     | 2025-01-30 | Team   | Initial runbook creation   |

---

**END OF RUNBOOK**

*Last Updated: 2025-01-30*
*Next Review: 2025-02-28*
