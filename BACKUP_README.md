# Backup System Documentation

## Overview

The AI Platform includes a comprehensive automated backup system that protects critical data across all databases:

- **Qdrant** - Vector database snapshots
- **Neo4j** - Graph database dumps  
- **PostgreSQL** - Relational database dumps

All backups are stored in MinIO (S3-compatible storage) with 30-day retention and automatic cleanup.

## Features

✅ **Automated Daily Backups** - Runs at 2 AM UTC daily  
✅ **30-Day Retention** - Automatic cleanup of old backups  
✅ **Checksums** - SHA256 verification for data integrity  
✅ **Metadata Tracking** - PostgreSQL table tracks all backups  
✅ **Easy Restoration** - Simple CLI tools for recovery  
✅ **Validation** - Automated integrity checks  
✅ **Disaster Recovery** - Complete runbook with procedures  

## Quick Start

### 1. Setup Backup System

```bash
# Initialize backup infrastructure
chmod +x backup_setup.sh
./backup_setup.sh
```

This will:
- Create necessary directories
- Initialize MinIO bucket
- Create backup history table
- Install dependencies
- Run test backup

### 2. Start Automated Backups

```bash
# Start backup service (runs daily at 2 AM)
docker compose up -d backup-service

# Check logs
docker compose logs -f backup-service
```

### 3. Run Manual Backup

```bash
# Run backup immediately
./backup_manual.sh

# Or using Python directly
python backup_service.py --run-once
```

### 4. List Available Backups

```bash
# List all backups
python restore_backup.py --list

# List specific type
python restore_backup.py --list --type qdrant
python restore_backup.py --list --type neo4j
python restore_backup.py --list --type postgres
```

### 5. Restore from Backup

```bash
# Interactive restore
./restore_manual.sh

# Or restore latest backups directly
python restore_backup.py --type all

# Restore specific database
python restore_backup.py --type qdrant
python restore_backup.py --type neo4j
python restore_backup.py --type postgres

# Restore specific backup by ID
python restore_backup.py --type postgres --backup-id postgres_20250130_020000
```

### 6. Validate Data Integrity

```bash
# Full integrity validation
python validate_data_integrity.py

# Quick validation only
python restore_backup.py --validate-only --type all
```

### 7. Run Smoke Tests

```bash
# Test all services after restore
chmod +x smoke_tests.sh
./smoke_tests.sh
```

## Architecture

### Backup Flow

```
┌─────────────────────────────────────────────────────────┐
│                   Backup Service                        │
│            (Scheduled: 2 AM UTC Daily)                  │
└─────────────┬───────────────────────────────────────────┘
              │
              ├─────────────────────────────────────────────┐
              │                                             │
┌─────────────▼─────────┐  ┌─────────────┐  ┌────────────▼─────────┐
│   Qdrant Snapshot     │  │   Neo4j     │  │  PostgreSQL pg_dump  │
│   (API-based)         │  │   Dump      │  │   (Custom format)    │
└─────────────┬─────────┘  └──────┬──────┘  └────────────┬─────────┘
              │                   │                       │
              └───────────────────┴───────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  Calculate SHA256 Checksum │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │   Upload to MinIO          │
                    │   (S3-compatible storage)  │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  Store Metadata            │
                    │  (PostgreSQL table)        │
                    └────────────────────────────┘
```

### Restore Flow

```
┌─────────────────────────────────────────────────────────┐
│               Restore Service (Manual)                  │
└─────────────┬───────────────────────────────────────────┘
              │
┌─────────────▼─────────────┐
│  List Available Backups   │
│  (MinIO + Metadata)       │
└─────────────┬─────────────┘
              │
┌─────────────▼─────────────┐
│  Download from MinIO      │
│  Verify Checksum          │
└─────────────┬─────────────┘
              │
              ├─────────────────────────────────────────────┐
              │                                             │
┌─────────────▼─────────┐  ┌─────────────┐  ┌────────────▼─────────┐
│   Qdrant Recovery     │  │   Neo4j     │  │  PostgreSQL Restore  │
│   (Upload snapshot)   │  │   Load      │  │   (pg_restore)       │
└─────────────┬─────────┘  └──────┬──────┘  └────────────┬─────────┘
              │                   │                       │
              └───────────────────┴───────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │  Validate Restoration      │
                    │  - Health checks           │
                    │  - Data integrity          │
                    │  - Cross-DB consistency    │
                    └────────────────────────────┘
```

## Components

### 1. Backup Service (`backup_service.py`)

Main service for automated backups.

**Features**:
- Scheduled backups (APScheduler)
- Snapshot creation for Qdrant
- Database dumps for Neo4j and PostgreSQL
- Upload to MinIO with metadata
- Checksum calculation
- Retention management (30 days)
- Metadata tracking in PostgreSQL

**Configuration** (Environment Variables):
```bash
BACKUP_SCHEDULE=0 2 * * *          # Cron format (2 AM daily)
BACKUP_RETENTION_DAYS=30           # Keep backups for 30 days
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
BACKUP_BUCKET=backups
```

**Usage**:
```bash
# Start service (scheduled)
python backup_service.py

# Run one-time backup
python backup_service.py --run-once
```

### 2. Restore Service (`restore_backup.py`)

CLI tool for restoring backups.

**Features**:
- List available backups
- Download from MinIO
- Restore to databases
- Checksum verification
- Post-restore validation

**Usage**:
```bash
# List backups
python restore_backup.py --list [--type qdrant|neo4j|postgres]

# Restore latest
python restore_backup.py --type all

# Restore specific backup
python restore_backup.py --type qdrant --backup-id qdrant_20250130_020000

# Validate only (no restore)
python restore_backup.py --validate-only --type all
```

### 3. Data Integrity Validator (`validate_data_integrity.py`)

Comprehensive validation of data integrity across all databases.

**Checks**:
- Database health and connectivity
- Data counts (vectors, nodes, rows)
- Schema integrity
- Cross-database consistency
- Orphaned records
- NULL values in critical fields
- Duplicate detection

**Usage**:
```bash
# Run full validation
python validate_data_integrity.py

# Generates report: validation_report_YYYYMMDD_HHMMSS.txt
```

**Example Report**:
```
========================================
DATA INTEGRITY VALIDATION REPORT
Generated: 2025-01-30T12:00:00
========================================

QDRANT VECTOR DATABASE
----------------------------------------
Status: PASSED
Health: ✓
Total Vectors: 1,234,567
Collections: 1
  - documents: 1,234,567 vectors

NEO4J GRAPH DATABASE
----------------------------------------
Status: PASSED
Health: ✓
Nodes: 45,678
Relationships: 89,012
Node Labels: 5
Relationship Types: 8

POSTGRESQL DATABASE
----------------------------------------
Status: PASSED
Health: ✓
Total Rows: 23,456
Tables: 8
  - feedback: 12,345 rows
  - lora_adapters: 23 rows
  - backup_history: 90 rows

OVERALL SUMMARY
========================================
✓ ALL VALIDATIONS PASSED
```

## Storage Structure

### MinIO Bucket Layout

```
backups/
├── qdrant/
│   ├── 2025/01/30/qdrant_20250130_020000.snapshot
│   ├── 2025/01/29/qdrant_20250129_020000.snapshot
│   └── ...
├── neo4j/
│   ├── 2025/01/30/neo4j_20250130_020000.dump
│   ├── 2025/01/29/neo4j_20250129_020000.dump
│   └── ...
└── postgres/
    ├── 2025/01/30/postgres_20250130_020000.dump
    ├── 2025/01/29/postgres_20250129_020000.dump
    └── ...
```

### PostgreSQL Backup History Table

```sql
CREATE TABLE backup_history (
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
```

**Query Examples**:
```sql
-- Recent backups
SELECT backup_type, timestamp, status, 
       size_bytes/1024/1024 as size_mb
FROM backup_history 
ORDER BY timestamp DESC 
LIMIT 10;

-- Failed backups in last 7 days
SELECT backup_type, COUNT(*) as failures
FROM backup_history 
WHERE status = 'failed' 
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY backup_type;

-- Total backup size by type
SELECT backup_type, 
       SUM(size_bytes)/1024/1024/1024 as total_gb,
       COUNT(*) as count
FROM backup_history
WHERE status = 'success'
GROUP BY backup_type;
```

## Backup Details by Database

### Qdrant Backups

**Method**: Qdrant Snapshot API  
**Format**: Binary snapshot file  
**Size**: ~250 MB (typical)  
**Time**: 5-15 minutes  

**Process**:
1. POST to `/snapshots` to create snapshot
2. GET snapshot file via `/snapshots/{name}`
3. Upload to MinIO
4. DELETE snapshot from Qdrant (cleanup)

**Restore**:
1. Download snapshot from MinIO
2. Upload to Qdrant via `/snapshots/upload`
3. Trigger recovery via `/snapshots/{name}/recover`

### Neo4j Backups

**Method**: `neo4j-admin database dump`  
**Format**: Compressed database dump  
**Size**: ~500 MB (typical)  
**Time**: 10-30 minutes  

**Process**:
1. Execute `neo4j-admin database dump neo4j`
2. Copy dump file from container
3. Upload to MinIO

**Restore**:
1. Download dump from MinIO
2. Stop Neo4j service
3. Execute `neo4j-admin database load neo4j`
4. Start Neo4j service

### PostgreSQL Backups

**Method**: `pg_dump` with custom format  
**Format**: Compressed custom format (.dump)  
**Size**: ~100 MB (typical)  
**Time**: 5-20 minutes  

**Process**:
1. Execute `pg_dump -F c` (custom compressed format)
2. Copy dump file from container
3. Upload to MinIO

**Restore**:
1. Download dump from MinIO
2. Terminate active connections
3. Drop and recreate database
4. Execute `pg_restore -F c`

## Retention and Cleanup

**Retention Period**: 30 days (configurable)  
**Cleanup Schedule**: Runs after each backup  
**Cleanup Logic**: Deletes backups older than retention period  

**Manual Cleanup**:
```python
from backup_service import BackupService
service = BackupService()
service.cleanup_old_backups()
```

## Monitoring

### Check Backup Status

```bash
# View recent backups
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT backup_type, timestamp, status 
  FROM backup_history 
  ORDER BY timestamp DESC 
  LIMIT 10;
"

# Check for failures
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT backup_type, COUNT(*) as failures
  FROM backup_history 
  WHERE status = 'failed' 
    AND timestamp > NOW() - INTERVAL '7 days'
  GROUP BY backup_type;
"
```

### Backup Service Logs

```bash
# View backup service logs
docker compose logs -f backup-service

# View last 100 lines
docker compose logs --tail=100 backup-service
```

### Grafana Dashboard

Create alerts in Grafana:
- Backup failures
- Missing backups (>25 hours)
- Large backup size changes
- Restore validation failures

## Disaster Recovery

See **[DISASTER_RECOVERY_RUNBOOK.md](DISASTER_RECOVERY_RUNBOOK.md)** for:
- Complete recovery procedures
- Common failure scenarios
- Troubleshooting guides
- RTO/RPO targets
- Escalation paths

**Quick Links**:
- [Assessment Procedures](DISASTER_RECOVERY_RUNBOOK.md#1-assess-the-situation)
- [Restore Procedures](DISASTER_RECOVERY_RUNBOOK.md#3-list-available-backups)
- [Validation Procedures](DISASTER_RECOVERY_RUNBOOK.md#5-validate-restoration)
- [Common Scenarios](DISASTER_RECOVERY_RUNBOOK.md#common-scenarios)
- [Troubleshooting](DISASTER_RECOVERY_RUNBOOK.md#troubleshooting)

## Testing

### Monthly DR Test

```bash
# 1. Create test environment
docker compose -f docker-compose.test.yaml up -d

# 2. Restore to test environment
export POSTGRES_HOST=postgres-test
export QDRANT_HOST=qdrant-test
export NEO4J_HOST=neo4j-test
python restore_backup.py --type all

# 3. Validate
python validate_data_integrity.py

# 4. Run smoke tests
./smoke_tests.sh

# 5. Document
echo "DR Test $(date): PASSED" >> dr_test_log.txt

# 6. Cleanup
docker compose -f docker-compose.test.yaml down -v
```

## Troubleshooting

### Backup Failures

**Problem**: Backup fails with timeout
```bash
# Check service logs
docker compose logs backup-service

# Increase timeout
export HTTPX_TIMEOUT=600

# Try manual backup
python backup_service.py --run-once
```

**Problem**: MinIO connection error
```bash
# Check MinIO health
curl http://localhost:9000/minio/health/live

# Restart MinIO
docker compose restart minio

# Verify credentials
docker compose exec backup-service env | grep MINIO
```

### Restore Failures

**Problem**: Restore hangs
```bash
# Check available disk space
df -h

# Check service logs
docker compose logs qdrant neo4j postgres

# Try restoring individual databases
python restore_backup.py --type qdrant
```

**Problem**: Validation fails after restore
```bash
# Run detailed integrity check
python validate_data_integrity.py

# Check for specific issues
docker compose logs api-server

# Try different backup
python restore_backup.py --list
python restore_backup.py --backup-id [older_backup]
```

## Security

### Credentials Management

**Production Setup**:
```bash
# Use strong credentials
export MINIO_ACCESS_KEY=$(openssl rand -base64 32)
export MINIO_SECRET_KEY=$(openssl rand -base64 32)

# Store in secure vault
# - AWS Secrets Manager
# - HashiCorp Vault
# - Kubernetes Secrets
```

### Encryption

**At Rest**:
- MinIO supports SSE (Server-Side Encryption)
- Enable encryption in MinIO configuration

**In Transit**:
- Use TLS for MinIO connections
- Use SSL for database connections

### Access Control

```bash
# Restrict backup service access
# Only backup-service should have MinIO write access
# Restore operations require manual approval
```

## Performance

### Backup Times (Typical)

| Database   | Size   | Backup Time | Upload Time | Total    |
|------------|--------|-------------|-------------|----------|
| Qdrant     | 500 MB | 5 min       | 2 min       | 7 min    |
| Neo4j      | 1 GB   | 10 min      | 3 min       | 13 min   |
| PostgreSQL | 200 MB | 5 min       | 1 min       | 6 min    |
| **Total**  | 1.7 GB | **20 min**  | **6 min**   | **26 min**|

### Restore Times (Typical)

| Database   | Download | Restore | Validation | Total    |
|------------|----------|---------|------------|----------|
| Qdrant     | 2 min    | 5 min   | 2 min      | 9 min    |
| Neo4j      | 3 min    | 15 min  | 5 min      | 23 min   |
| PostgreSQL | 1 min    | 10 min  | 3 min      | 14 min   |
| **Total**  | **6 min**| **30 min**| **10 min** | **46 min**|

## FAQ

**Q: How often are backups taken?**  
A: Daily at 2 AM UTC. Configurable via `BACKUP_SCHEDULE`.

**Q: How long are backups retained?**  
A: 30 days. Configurable via `BACKUP_RETENTION_DAYS`.

**Q: Can I restore to a different environment?**  
A: Yes, by setting appropriate environment variables before restore.

**Q: What if a backup is corrupted?**  
A: Each backup has a SHA256 checksum. Restore will fail if checksum doesn't match. Use a different backup.

**Q: Can I restore individual tables?**  
A: For PostgreSQL, yes, using `pg_restore -t table_name`. For Qdrant and Neo4j, full restore only.

**Q: How do I test backups without affecting production?**  
A: Use a test environment with separate database instances.

**Q: What's the RTO (Recovery Time Objective)?**  
A: Full system: <60 minutes. Individual databases: 15-30 minutes.

**Q: What's the RPO (Recovery Point Objective)?**  
A: 24 hours (daily backups). For lower RPO, increase backup frequency.

## Support

For issues or questions:
1. Check logs: `docker compose logs backup-service`
2. Review runbook: [DISASTER_RECOVERY_RUNBOOK.md](DISASTER_RECOVERY_RUNBOOK.md)
3. Run validation: `python validate_data_integrity.py`
4. Contact platform team

## License

Same as main project.

---

**Last Updated**: 2025-01-30  
**Version**: 1.0
