# Backup System Quick Start Guide

Get the automated backup system up and running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.8+ with pip
- AI Platform services running

## Setup (One-Time)

### Step 1: Initialize Backup System

```bash
# Make setup script executable and run it
chmod +x backup_setup.sh
./backup_setup.sh
```

This will:
- Create backup directories
- Install Python dependencies
- Initialize MinIO bucket
- Create backup history table
- Run test backup

### Step 2: Start Backup Service

```bash
# Start automated backup service
docker compose up -d backup-service

# Verify it's running
docker compose ps backup-service
```

### Step 3: Verify Setup

```bash
# Check logs
docker compose logs backup-service

# List backups (should see test backup)
python restore_backup.py --list
```

✅ **Setup Complete!** Backups will now run automatically at 2 AM UTC daily.

---

## Common Tasks

### Run Manual Backup

```bash
./backup_manual.sh
```

### List Available Backups

```bash
# All backups
python restore_backup.py --list

# Specific type
python restore_backup.py --list --type qdrant
python restore_backup.py --list --type neo4j
python restore_backup.py --list --type postgres
```

### Restore from Backup

```bash
# Interactive restore menu
./restore_manual.sh

# Or restore latest backups directly
python restore_backup.py --type all

# Restore specific database
python restore_backup.py --type qdrant
python restore_backup.py --type neo4j
python restore_backup.py --type postgres
```

### Validate System Health

```bash
# Run integrity validation
python validate_data_integrity.py

# Run smoke tests
./smoke_tests.sh

# Quick validation
python restore_backup.py --validate-only --type all
```

---

## Monitoring

### Check Recent Backups

```bash
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT backup_type, timestamp, status, size_bytes/1024/1024 as size_mb 
  FROM backup_history 
  ORDER BY timestamp DESC 
  LIMIT 10;
"
```

### Check for Failures

```bash
docker exec postgres psql -U ai_user -d ai_platform -c "
  SELECT backup_type, COUNT(*) as failures
  FROM backup_history 
  WHERE status = 'failed' 
    AND timestamp > NOW() - INTERVAL '7 days'
  GROUP BY backup_type;
"
```

### Monitor Backup Service

```bash
# Follow logs in real-time
docker compose logs -f backup-service

# View last 100 lines
docker compose logs --tail=100 backup-service
```

---

## Emergency Recovery

### Scenario: Need to Restore Everything

```bash
# 1. List available backups
python restore_backup.py --list

# 2. Stop all services
docker compose stop

# 3. Restore from latest backups
python restore_backup.py --type all

# 4. Validate restoration
python validate_data_integrity.py

# 5. Restart services
docker compose up -d

# 6. Run smoke tests
./smoke_tests.sh
```

### Scenario: Restore Single Database

```bash
# For Qdrant
docker compose stop api-server gateway
python restore_backup.py --type qdrant
python restore_backup.py --validate-only --type qdrant
docker compose start api-server gateway

# For Neo4j
docker compose stop api-server
python restore_backup.py --type neo4j
python restore_backup.py --validate-only --type neo4j
docker compose start api-server

# For PostgreSQL
docker compose stop
python restore_backup.py --type postgres
python restore_backup.py --validate-only --type postgres
docker compose up -d
```

---

## Configuration

### Change Backup Schedule

Edit `docker-compose.yaml`:

```yaml
environment:
  - BACKUP_SCHEDULE=0 3 * * *    # 3 AM daily
  # OR
  - BACKUP_SCHEDULE=0 */6 * * *  # Every 6 hours
  # OR
  - BACKUP_SCHEDULE=0 2 * * 0    # Weekly on Sunday
```

Then restart:
```bash
docker compose restart backup-service
```

### Change Retention Period

Edit `docker-compose.yaml`:

```yaml
environment:
  - BACKUP_RETENTION_DAYS=60     # Keep for 60 days
  # OR
  - BACKUP_RETENTION_DAYS=7      # Keep for 7 days
```

Then restart:
```bash
docker compose restart backup-service
```

---

## Troubleshooting

### Backup Service Not Running

```bash
# Check status
docker compose ps backup-service

# Check logs
docker compose logs backup-service

# Restart service
docker compose restart backup-service
```

### No Backups Appearing

```bash
# Check MinIO is running
docker compose ps minio
curl http://localhost:9000/minio/health/live

# Check backup service logs
docker compose logs backup-service

# Run manual backup
./backup_manual.sh
```

### Restore Fails

```bash
# Check disk space
df -h

# Check database services
docker compose ps

# Try restore with validation only
python restore_backup.py --validate-only --type all

# Check detailed logs
docker compose logs qdrant neo4j postgres
```

---

## Next Steps

1. **Read Full Documentation**:
   - [BACKUP_README.md](BACKUP_README.md) - Complete system guide
   - [DISASTER_RECOVERY_RUNBOOK.md](DISASTER_RECOVERY_RUNBOOK.md) - Recovery procedures

2. **Setup Monitoring**:
   - Configure Grafana alerts
   - Add Slack notifications
   - Monitor backup success rates

3. **Test Recovery**:
   - Schedule monthly DR tests
   - Document recovery procedures
   - Train team on restore process

4. **Production Hardening**:
   - Use strong MinIO credentials
   - Enable encryption at rest
   - Setup multi-region replication

---

## Key Files

| File | Purpose |
|------|---------|
| `backup_setup.sh` | One-time setup |
| `backup_manual.sh` | Manual backup trigger |
| `restore_manual.sh` | Interactive restore |
| `smoke_tests.sh` | Health verification |
| `backup_service.py` | Main backup service |
| `restore_backup.py` | Restore CLI tool |
| `validate_data_integrity.py` | Integrity checker |

---

## Support

**Quick Help**:
```bash
# Service status
docker compose ps

# Logs
docker compose logs backup-service

# List backups
python restore_backup.py --list

# Validate system
python validate_data_integrity.py
```

**Documentation**:
- Setup: [BACKUP_README.md](BACKUP_README.md)
- Recovery: [DISASTER_RECOVERY_RUNBOOK.md](DISASTER_RECOVERY_RUNBOOK.md)
- Details: [BACKUP_IMPLEMENTATION.md](BACKUP_IMPLEMENTATION.md)

---

## Summary

✅ **Automated**: Daily backups at 2 AM UTC  
✅ **Retention**: 30 days automatic cleanup  
✅ **Storage**: MinIO (S3-compatible)  
✅ **Databases**: Qdrant, Neo4j, PostgreSQL  
✅ **Verification**: SHA256 checksums  
✅ **Recovery**: Simple CLI tools  
✅ **Validation**: Automated integrity checks  

**You're all set!** The backup system will protect your data automatically.
