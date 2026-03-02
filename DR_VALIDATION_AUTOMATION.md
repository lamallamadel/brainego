# Disaster Recovery Validation Automation

Comprehensive disaster recovery validation automation for the AI Platform that simulates complete region failure and validates recovery procedures.

## Overview

The DR validation automation provides:

1. **Cross-Region Backup Replication Verification** - Extended `test_backup_restore.py`
2. **Complete DR Drill Simulation** - New `scripts/backup/dr_drill.py`
3. **Data Integrity Validation** - Checksums and row count verification
4. **RTO Testing** - 1-hour recovery time objective validation
5. **Gap Analysis** - Automated identification of recovery gaps
6. **Automated Reporting** - Comprehensive drill reports with recommendations

## Components

### 1. Extended Backup/Restore Tests

**File**: `test_backup_restore.py`

**New Features**:
- Cross-region backup replication verification
- S3/MinIO checksum validation across regions
- Replication coverage metrics (>95% threshold)
- Detection of missing or corrupted backups

**Usage**:
```bash
# Set secondary region for cross-region tests
export SECONDARY_MINIO_ENDPOINT=minio-secondary:9000

# Run extended tests
python test_backup_restore.py
```

**Test Coverage**:
- ✅ Backup creation
- ✅ Data restoration  
- ✅ Zero data loss verification
- ✅ Cross-region replication (NEW)
- ✅ Checksum integrity across regions (NEW)

### 2. DR Drill Script

**File**: `scripts/backup/dr_drill.py`

**Capabilities**:
- Simulates complete region failure
- Restores all StatefulSets (PostgreSQL, Qdrant, Neo4j) from MinIO backups
- Validates data integrity with SHA256 checksums
- Verifies row counts and point counts
- Tests against 1-hour RTO target
- Generates comprehensive reports

**Usage**:
```bash
# Basic DR drill
python scripts/backup/dr_drill.py

# With custom DR cluster configuration
python scripts/backup/dr_drill.py --new-cluster-config dr_cluster.json

# Using helper script
bash scripts/backup/run_dr_drill.sh --config dr_cluster.json
```

### 3. DR Drill Process

The DR drill executes in three phases:

#### Phase 1: PostgreSQL Restoration
```
1. Download latest backup from MinIO
2. Calculate SHA256 checksum
3. Connect to DR cluster
4. Drop/recreate database
5. Restore using pg_restore
6. Validate row counts
7. Record duration
```

#### Phase 2: Qdrant Restoration
```
1. Download latest snapshot from MinIO
2. Calculate SHA256 checksum
3. Upload snapshot to DR Qdrant cluster
4. Trigger recovery process
5. Validate point counts across collections
6. Record duration
```

#### Phase 3: Neo4j Restoration
```
1. Download latest dump from MinIO
2. Calculate SHA256 checksum
3. Stop Neo4j service
4. Load dump using neo4j-admin
5. Start Neo4j service
6. Validate service availability
7. Record duration
```

## Configuration

### Environment Variables

```bash
# MinIO/S3 Configuration
export MINIO_ENDPOINT=minio:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin123
export BACKUP_BUCKET=backups

# Secondary Region (for cross-region tests)
export SECONDARY_MINIO_ENDPOINT=minio-secondary:9000

# DR Cluster Configuration
export DR_POSTGRES_HOST=dr-postgres.example.com
export DR_POSTGRES_PORT=5432
export DR_POSTGRES_DB=ai_platform_dr
export DR_POSTGRES_USER=ai_user
export DR_POSTGRES_PASSWORD=secure_password
export DR_QDRANT_HOST=dr-qdrant.example.com
export DR_QDRANT_PORT=6333
export DR_NEO4J_HOST=dr-neo4j.example.com
export DR_NEO4J_USER=neo4j
export DR_NEO4J_PASSWORD=secure_password
```

### DR Cluster Configuration File

Create `dr_cluster_config.json`:

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

## DR Drill Report

### Report Structure

```json
{
  "drill_id": "dr_drill_20240115_143022",
  "start_time": "2024-01-15T14:30:22.123456Z",
  "end_time": "2024-01-15T14:58:15.987654Z",
  "total_duration_seconds": 1673.86,
  "rto_target_seconds": 3600,
  "rto_met": true,
  "data_integrity_verified": true,
  "results": [
    {
      "database": "postgresql",
      "operation": "restore",
      "start_time": "2024-01-15T14:30:22.123456Z",
      "end_time": "2024-01-15T14:44:07.456789Z",
      "duration_seconds": 845.33,
      "status": "success",
      "backup_size_bytes": 524288000,
      "checksum_before": "abc123def456...",
      "checksum_after": "abc123def456...",
      "row_count_before": null,
      "row_count_after": 150000,
      "error_message": null
    },
    {
      "database": "qdrant",
      "operation": "restore",
      "start_time": "2024-01-15T14:44:07.456789Z",
      "end_time": "2024-01-15T14:52:15.789012Z",
      "duration_seconds": 488.33,
      "status": "success",
      "backup_size_bytes": 314572800,
      "checksum_before": "def789ghi012...",
      "checksum_after": "def789ghi012...",
      "row_count_before": null,
      "row_count_after": 50000,
      "error_message": null
    },
    {
      "database": "neo4j",
      "operation": "restore",
      "start_time": "2024-01-15T14:52:15.789012Z",
      "end_time": "2024-01-15T14:58:15.987654Z",
      "duration_seconds": 360.20,
      "status": "success",
      "backup_size_bytes": 209715200,
      "checksum_before": "ghi345jkl678...",
      "checksum_after": "ghi345jkl678...",
      "row_count_before": null,
      "row_count_after": null,
      "error_message": null
    }
  ],
  "identified_gaps": [],
  "recommendations": [
    "Consider parallel restoration of databases to reduce total RTO",
    "Set up automated DR drill scheduling (quarterly minimum)",
    "Implement real-time backup validation to detect corruption early"
  ]
}
```

### Report Metrics

#### Success Criteria
- ✅ **RTO Met**: Total duration ≤ 3600 seconds (1 hour)
- ✅ **Data Integrity**: All checksums match before/after
- ✅ **Data Completeness**: Row/point counts > 0
- ✅ **Zero Failures**: All operations succeed
- ✅ **No Critical Gaps**: No blocking issues identified

#### Identified Gaps

The drill automatically identifies:

1. **Failed Restore Operations**
   - Database restore failures
   - Service startup failures
   - Connection failures

2. **RTO Violations**
   - Total duration exceeds 1 hour
   - Individual operations too slow
   - Specific time exceeded by

3. **Data Integrity Issues**
   - Missing checksums
   - Checksum mismatches
   - Zero data restored

4. **Infrastructure Issues**
   - Missing backup files
   - S3/MinIO connection failures
   - DR cluster unavailability

#### Recommendations

Automated recommendations include:

1. **Performance Optimization**
   - Parallel restoration
   - Backup compression optimization
   - Network bandwidth improvements

2. **Reliability Improvements**
   - Automated retry logic
   - Incremental backups
   - Backup validation

3. **Operational Best Practices**
   - Scheduled drill automation
   - Real-time monitoring
   - Alert configuration

## Automation

### GitHub Actions Integration

The DR drill runs automatically on a quarterly schedule via `.github/workflows/dr-drill.yml`:

```yaml
name: Disaster Recovery Drill

on:
  schedule:
    # Quarterly: Jan 1, Apr 1, Jul 1, Oct 1 at 2 AM UTC
    - cron: '0 2 1 1,4,7,10 *'
  workflow_dispatch:  # Manual trigger
```

**Features**:
- Automated quarterly execution
- Manual trigger capability
- Comprehensive reporting
- Artifact retention (90 days)
- Automatic issue creation on failure

### Manual Execution

```bash
# Using Python directly
python scripts/backup/dr_drill.py

# Using helper script (recommended)
bash scripts/backup/run_dr_drill.sh

# With custom configuration
bash scripts/backup/run_dr_drill.sh --config dr_cluster.json
```

## Validation Workflow

### Pre-Drill Checklist

- [ ] MinIO/S3 accessible with valid credentials
- [ ] Latest backups available for all databases
- [ ] DR cluster provisioned and accessible
- [ ] Network connectivity verified
- [ ] Sufficient disk space on DR cluster
- [ ] Credentials configured correctly

### During Drill

The script automatically:
1. ✅ Downloads backups from MinIO
2. ✅ Validates checksums
3. ✅ Restores to DR cluster
4. ✅ Validates data integrity
5. ✅ Records timing metrics
6. ✅ Generates report

### Post-Drill Actions

1. **Review Report**
   - Check RTO compliance
   - Verify data integrity
   - Analyze identified gaps

2. **Address Gaps**
   - Fix identified issues
   - Update procedures
   - Improve automation

3. **Update Documentation**
   - Record lessons learned
   - Update runbooks
   - Revise procedures

4. **Communicate Results**
   - Share with stakeholders
   - Update SLA documentation
   - Plan improvements

## Monitoring & Alerting

### Key Metrics

Track over time:
- **RTO**: Recovery time (target: < 1 hour)
- **RPO**: Data loss (target: 0)
- **Success Rate**: Drill pass rate (target: 100%)
- **Backup Size**: Trend analysis
- **Restore Speed**: Throughput optimization

### Alerts

Set up alerts for:
- DR drill failures
- RTO violations
- Data integrity issues
- Missing backups
- Replication lag

## Best Practices

1. **Regular Testing**
   - Quarterly DR drills minimum
   - After major infrastructure changes
   - Following backup system updates

2. **Production-Like Environment**
   - Realistic data volumes
   - Similar network conditions
   - Representative workload

3. **Full Scope Testing**
   - All databases and services
   - Complete data sets
   - All dependencies

4. **Documentation**
   - Keep runbooks updated
   - Document all gaps
   - Track improvements

5. **Continuous Improvement**
   - Act on recommendations
   - Optimize performance
   - Automate manual steps

## Troubleshooting

### Common Issues

**Issue**: S3/MinIO connection timeout
```bash
# Verify endpoint
curl http://$MINIO_ENDPOINT/minio/health/live

# Check network
ping $MINIO_ENDPOINT

# Verify credentials
aws s3 ls --endpoint-url http://$MINIO_ENDPOINT
```

**Issue**: PostgreSQL restore fails
```bash
# Check connectivity
pg_isready -h $DR_POSTGRES_HOST -p $DR_POSTGRES_PORT

# Verify permissions
psql -h $DR_POSTGRES_HOST -U $DR_POSTGRES_USER -d postgres -c '\du'

# Check disk space
psql -h $DR_POSTGRES_HOST -U $DR_POSTGRES_USER -d postgres -c "SELECT pg_size_pretty(pg_database_size('postgres'))"
```

**Issue**: Qdrant snapshot upload fails
```bash
# Check Qdrant health
curl http://$DR_QDRANT_HOST:$DR_QDRANT_PORT/health

# Check disk space
curl http://$DR_QDRANT_HOST:$DR_QDRANT_PORT/metrics | grep disk

# Check upload limits
curl http://$DR_QDRANT_HOST:$DR_QDRANT_PORT/cluster
```

**Issue**: Neo4j restore hangs
```bash
# Check Neo4j status
docker exec neo4j neo4j status

# View logs
docker logs neo4j --tail 100 --follow

# Check memory
docker stats neo4j
```

## Security Considerations

1. **Credential Management**
   - Use secrets management (Vault, AWS Secrets Manager)
   - Rotate credentials regularly
   - Audit access logs

2. **Network Security**
   - Use TLS/SSL for all connections
   - Restrict DR cluster access
   - Enable VPN for cross-region

3. **Data Protection**
   - Encrypt backups at rest
   - Encrypt data in transit
   - Validate checksums

4. **Access Control**
   - Limit DR drill execution permissions
   - Require approval for production drills
   - Log all activities

5. **Compliance**
   - Document DR procedures
   - Maintain audit trail
   - Meet regulatory requirements

## Related Documentation

- [Backup Service](backup_service.py)
- [Restore Service](restore_backup.py)
- [Backup Testing](test_backup_restore.py)
- [Disaster Recovery Runbook](DISASTER_RECOVERY_RUNBOOK.md)
- [DR Drill Script](scripts/backup/dr_drill.py)
- [DR Drill README](scripts/backup/README.md)

## Dependencies

### Python Packages

Required packages (already in `vendor/wheels/`):
- `boto3` - AWS S3/MinIO client
- `botocore` - AWS SDK core
- `psycopg2-binary` - PostgreSQL driver
- `httpx` - HTTP client for Qdrant API
- `qdrant-client` - Qdrant Python client

If not available:
```bash
# Needs: python-package:boto3>=1.28.0
# Needs: python-package:botocore>=1.31.0
# Needs: python-package:psycopg2-binary>=2.9.0
# Needs: python-package:httpx>=0.24.0
# Needs: python-package:qdrant-client>=1.6.0
```

### External Services

Required for DR drills:
- MinIO/S3 (backup storage)
- PostgreSQL (DR cluster)
- Qdrant (DR cluster)
- Neo4j (DR cluster)
- Docker (for service management)

## Metrics & KPIs

### Recovery Time Objective (RTO)

**Target**: 1 hour (3600 seconds)

**Measurement**: Total time from drill start to complete restoration

**Current Performance**: Track in each drill report

### Recovery Point Objective (RPO)

**Target**: 0 data loss

**Measurement**: Data integrity verification via checksums and row counts

**Current Performance**: 100% (all checksums match)

### Availability SLO

**Target**: 99.9% uptime

**DR Impact**: DR drill validates ability to meet SLO after failure

### Data Integrity SLO

**Target**: 100% data integrity

**Measurement**: Checksum validation + row count comparison

## Conclusion

The DR validation automation provides comprehensive disaster recovery testing that:

- ✅ Simulates complete region failure
- ✅ Validates 1-hour RTO compliance
- ✅ Ensures data integrity with checksums
- ✅ Identifies gaps automatically
- ✅ Provides actionable recommendations
- ✅ Runs automatically on schedule
- ✅ Generates detailed reports

This automation ensures the AI Platform can recover from catastrophic failures within SLA requirements while maintaining zero data loss.
