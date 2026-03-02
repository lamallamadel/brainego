# Disaster Recovery Automation

Comprehensive disaster recovery validation automation for the AI Platform.

## Overview

This directory contains scripts for disaster recovery (DR) drills that simulate complete region failure and validate backup restoration procedures.

## Components

### 1. DR Drill Script (`dr_drill.py`)

Simulates a complete region failure by:
- Restoring all StatefulSet data (PostgreSQL, Qdrant, Neo4j) from MinIO backups
- Validating data integrity with checksums and row counts
- Testing backup restoration within RTO target of 1 hour
- Generating comprehensive DR drill reports with identified gaps

### 2. Extended Backup Tests (`../../test_backup_restore.py`)

Enhanced with cross-region backup replication verification:
- Verifies backups are replicated to secondary region
- Validates checksum integrity across regions
- Ensures >95% replication coverage
- Detects missing or corrupted backups

## Usage

### Running a DR Drill

```bash
# Basic DR drill (uses default/current cluster)
python scripts/backup/dr_drill.py

# DR drill with custom new cluster configuration
python scripts/backup/dr_drill.py --new-cluster-config dr_cluster_config.json
```

### New Cluster Configuration

Create a JSON file with failover cluster details:

```json
{
  "postgres_host": "dr-postgres.example.com",
  "postgres_port": 5432,
  "postgres_db": "ai_platform_dr",
  "postgres_user": "ai_user",
  "postgres_password": "secure_password",
  "qdrant_host": "dr-qdrant.example.com",
  "qdrant_port": 6333,
  "neo4j_host": "dr-neo4j.example.com",
  "neo4j_user": "neo4j",
  "neo4j_password": "secure_password"
}
```

### Environment Variables

Configure DR drill behavior with environment variables:

```bash
# MinIO/S3 Configuration
export MINIO_ENDPOINT=minio:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin123
export BACKUP_BUCKET=backups

# Secondary Region for Cross-Region Replication Tests
export SECONDARY_MINIO_ENDPOINT=minio-secondary:9000

# DR Cluster Configuration (alternative to config file)
export DR_POSTGRES_HOST=localhost
export DR_POSTGRES_PORT=5432
export DR_POSTGRES_DB=ai_platform_dr
export DR_POSTGRES_USER=ai_user
export DR_POSTGRES_PASSWORD=ai_password
export DR_QDRANT_HOST=localhost
export DR_QDRANT_PORT=6333
export DR_NEO4J_HOST=localhost
export DR_NEO4J_USER=neo4j
export DR_NEO4J_PASSWORD=neo4j_password
```

## DR Drill Process

The DR drill executes the following phases:

### Phase 1: PostgreSQL Restore
1. Download latest PostgreSQL backup from MinIO
2. Calculate and verify checksum
3. Drop and recreate database on new cluster
4. Restore using pg_restore
5. Validate row counts

### Phase 2: Qdrant Restore
1. Download latest Qdrant snapshot from MinIO
2. Calculate and verify checksum
3. Upload snapshot to new Qdrant cluster
4. Trigger recovery process
5. Validate point counts

### Phase 3: Neo4j Restore
1. Download latest Neo4j dump from MinIO
2. Calculate and verify checksum
3. Stop Neo4j service
4. Load dump using neo4j-admin
5. Start Neo4j service
6. Validate service availability

## Report Output

The DR drill generates a comprehensive JSON report:

```json
{
  "drill_id": "dr_drill_20240115_143022",
  "start_time": "2024-01-15T14:30:22Z",
  "end_time": "2024-01-15T14:58:15Z",
  "total_duration_seconds": 1673.5,
  "rto_target_seconds": 3600,
  "rto_met": true,
  "data_integrity_verified": true,
  "results": [
    {
      "database": "postgresql",
      "operation": "restore",
      "duration_seconds": 845.2,
      "status": "success",
      "backup_size_bytes": 524288000,
      "checksum_before": "abc123...",
      "checksum_after": "abc123...",
      "row_count_after": 150000
    }
  ],
  "identified_gaps": [],
  "recommendations": [
    "Consider parallel restoration of databases to reduce total RTO",
    "Set up automated DR drill scheduling (quarterly minimum)"
  ]
}
```

## Success Criteria

A DR drill is considered successful when:

1. **RTO Compliance**: Total restoration time ≤ 1 hour (3600 seconds)
2. **Data Integrity**: All checksums match before/after restoration
3. **Data Completeness**: Row/point counts > 0 for all databases
4. **Zero Failures**: All restore operations complete successfully
5. **No Gaps**: No critical gaps identified in the process

## Identified Gaps

The drill automatically identifies and reports:

- Failed restore operations
- RTO target violations
- Missing or corrupted checksums
- Checksum mismatches
- Zero data restored
- Missing backup files
- Configuration issues

## Recommendations

The drill provides actionable recommendations:

- **Performance**: Parallel restoration, backup optimization
- **Reliability**: Automated retry logic, incremental backups
- **Operations**: Scheduled drills, real-time validation
- **Monitoring**: Backup health checks, alerting

## Integration with CI/CD

### Scheduled DR Drills

Run automated DR drills on a schedule:

```yaml
# .github/workflows/dr-drill.yml
name: DR Drill
on:
  schedule:
    - cron: '0 2 1 */3 *'  # Quarterly at 2 AM on 1st day

jobs:
  dr-drill:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run DR Drill
        run: python scripts/backup/dr_drill.py
      - name: Upload Report
        uses: actions/upload-artifact@v2
        with:
          name: dr-drill-report
          path: dr_drill_report_*.json
```

## Best Practices

1. **Regular Testing**: Run DR drills quarterly minimum
2. **Production-Like Environment**: Use realistic data volumes
3. **Full Scope**: Test all databases and services
4. **Document Results**: Review and act on identified gaps
5. **Update Runbooks**: Keep disaster recovery procedures current
6. **Monitor Trends**: Track RTO and data volumes over time
7. **Test Failback**: Also test returning to primary region

## Troubleshooting

### Common Issues

**S3/MinIO Connection Failures**
```bash
# Verify MinIO endpoint
curl http://$MINIO_ENDPOINT/minio/health/live

# Check credentials
aws s3 ls s3://backups --endpoint-url http://$MINIO_ENDPOINT
```

**PostgreSQL Restore Failures**
```bash
# Check network connectivity
pg_isready -h $DR_POSTGRES_HOST -p $DR_POSTGRES_PORT

# Verify credentials
psql -h $DR_POSTGRES_HOST -U $DR_POSTGRES_USER -d postgres -c '\l'
```

**Qdrant Snapshot Upload Failures**
```bash
# Check Qdrant health
curl http://$DR_QDRANT_HOST:$DR_QDRANT_PORT/health

# Check available disk space
curl http://$DR_QDRANT_HOST:$DR_QDRANT_PORT/metrics
```

**Neo4j Restore Failures**
```bash
# Check Neo4j status
docker exec neo4j neo4j status

# Check logs
docker logs neo4j --tail 100
```

## Security Considerations

1. **Credentials**: Use secrets management (Vault, AWS Secrets Manager)
2. **Network**: Ensure secure connections (TLS/SSL)
3. **Access Control**: Limit DR drill execution permissions
4. **Audit Trail**: Log all DR drill activities
5. **Data Protection**: Encrypt backups at rest and in transit

## Related Documentation

- [Backup Service](../../backup_service.py)
- [Restore Service](../../restore_backup.py)
- [Backup Testing](../../test_backup_restore.py)
- [Disaster Recovery Runbook](../../DISASTER_RECOVERY_RUNBOOK.md)
