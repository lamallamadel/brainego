# DR Drill Quick Start Guide

Quick reference for running disaster recovery drills.

## Prerequisites

```bash
# Install required packages (if not already available)
pip install boto3 psycopg2-binary httpx qdrant-client
```

## Quick Run

### Option 1: Using Helper Script (Recommended)

```bash
# Basic drill (uses current cluster)
bash scripts/backup/run_dr_drill.sh

# With custom DR cluster
bash scripts/backup/run_dr_drill.sh --config dr_cluster.json
```

### Option 2: Direct Python

```bash
# Basic drill
python scripts/backup/dr_drill.py

# With configuration file
python scripts/backup/dr_drill.py --new-cluster-config dr_cluster.json
```

## Environment Setup

```bash
# Minimal required configuration
export MINIO_ENDPOINT=minio:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin123

# DR cluster configuration
export DR_POSTGRES_HOST=localhost
export DR_POSTGRES_PORT=5432
export DR_QDRANT_HOST=localhost
export DR_QDRANT_PORT=6333
export DR_NEO4J_HOST=localhost
```

## Expected Output

```
========================================
DISASTER RECOVERY DRILL: dr_drill_20240115_143022
========================================
RTO Target: 3600s (60.0 minutes)
========================================

Phase 1: Restore PostgreSQL
...
✓ PostgreSQL restored in 845.33 seconds
  Row count: 150,000

Phase 2: Restore Qdrant
...
✓ Qdrant restored in 488.33 seconds
  Point count: 50,000

Phase 3: Restore Neo4j
...
✓ Neo4j restored in 360.20 seconds

========================================
ANALYZING RESULTS
========================================
...

========================================
DISASTER RECOVERY DRILL REPORT
========================================
✓ RTO TARGET MET
✓ DATA INTEGRITY VERIFIED
```

## Report Location

Reports are saved as: `dr_drill_report_<drill_id>.json`

Example: `dr_drill_report_dr_drill_20240115_143022.json`

## Success Criteria

✅ RTO Met (< 1 hour)
✅ Data Integrity Verified
✅ All Databases Restored
✅ No Critical Gaps

## Common Commands

```bash
# List available backups
aws s3 ls s3://backups/ --endpoint-url http://minio:9000 --recursive

# Check DR cluster connectivity
pg_isready -h $DR_POSTGRES_HOST -p $DR_POSTGRES_PORT
curl http://$DR_QDRANT_HOST:$DR_QDRANT_PORT/health
docker exec neo4j neo4j status

# View latest report
cat dr_drill_report_*.json | jq '.'
```

## Troubleshooting

### No backups found
```bash
# Verify MinIO connection
curl http://$MINIO_ENDPOINT/minio/health/live

# Create test backup
python backup_service.py --run-once
```

### Connection failures
```bash
# Test PostgreSQL
psql -h $DR_POSTGRES_HOST -U $DR_POSTGRES_USER -d postgres -c '\l'

# Test Qdrant
curl http://$DR_QDRANT_HOST:$DR_QDRANT_PORT/collections

# Test Neo4j
docker exec neo4j cypher-shell -u neo4j -p $DR_NEO4J_PASSWORD "RETURN 1"
```

### RTO exceeded
- Consider parallel restoration
- Optimize network bandwidth
- Use incremental backups
- Increase DR cluster resources

## Next Steps

1. Review the generated report
2. Address any identified gaps
3. Schedule regular drills (quarterly)
4. Update DR procedures
5. Communicate results to stakeholders

## Help

For detailed documentation, see:
- [DR Validation Automation](../../DR_VALIDATION_AUTOMATION.md)
- [Backup Scripts README](README.md)
- [Disaster Recovery Runbook](../../DISASTER_RECOVERY_RUNBOOK.md)
