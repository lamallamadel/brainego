# Docker Compose to Kubernetes Migration Guide

This guide provides comprehensive instructions for migrating the AI Platform from Docker Compose to Kubernetes, including data migration, validation, and rollback procedures.

## Overview

The migration script (`migrate_to_k8s.py`) automates the complete migration process:

1. **Export**: Export all Docker Compose volumes to tar archives
2. **Validate**: Verify data integrity with checksums and pattern matching
3. **Import**: Create Kubernetes PVCs and import data
4. **Rollback**: Restore Docker Compose environment if needed

## Prerequisites

### Required Tools

- **Docker**: Running with access to Docker volumes
- **kubectl**: Configured for target Kubernetes cluster
- **Python 3.8+**: With required dependencies
- **PyYAML**: `pip install pyyaml`

### Cluster Requirements

- Kubernetes cluster 1.20+
- Storage provisioner (for dynamic PVC creation)
- Sufficient storage capacity (see volume sizes below)
- Namespace `ai-platform` created or will be created

### Storage Requirements

Total storage needed: ~270 GB

| Volume | Size | Contents |
|--------|------|----------|
| postgres-data | 20 GB | PostgreSQL database |
| qdrant-storage | 50 GB | Vector embeddings |
| redis-data | 10 GB | Cache and queues |
| minio-data | 100 GB | Object storage |
| neo4j-data | 30 GB | Graph database |
| neo4j-logs | 5 GB | Neo4j logs |
| jaeger-data | 20 GB | Tracing data |
| prometheus-data | 30 GB | Metrics |
| grafana-data | 5 GB | Dashboards |

## Quick Start

### Full Migration (Recommended)

```bash
# Complete migration workflow
python migrate_to_k8s.py full

# This will:
# 1. Create backup of current state
# 2. Export all volumes
# 3. Validate exports
# 4. Import to Kubernetes
# 5. Generate report
```

### Step-by-Step Migration

For more control, run each phase separately:

```bash
# Step 1: Export Docker volumes
python migrate_to_k8s.py export

# Step 2: Validate exports
python migrate_to_k8s.py validate

# Step 3: Import to Kubernetes
python migrate_to_k8s.py import

# Check migration status
python migrate_to_k8s.py report
```

## Detailed Usage

### Command Reference

```bash
# Export volumes
python migrate_to_k8s.py export [--work-dir PATH]

# Validate exported data
python migrate_to_k8s.py validate [--work-dir PATH]

# Import to Kubernetes
python migrate_to_k8s.py import [--work-dir PATH]

# Rollback to Docker Compose
python migrate_to_k8s.py rollback [--work-dir PATH]

# Generate report
python migrate_to_k8s.py report [--work-dir PATH]

# Full migration workflow
python migrate_to_k8s.py full [--work-dir PATH]
```

### Options

- `--work-dir PATH`: Working directory for migration files (default: `./migration_work`)

## Migration Phases

### Phase 1: Export

Exports all Docker Compose volumes to tar.gz archives.

**What happens:**
- Creates temporary Alpine container for each volume
- Archives volume contents with tar
- Calculates SHA256 checksums
- Stores metadata in `migration_metadata.json`

**Output:**
```
migration_work/
├── exports/
│   ├── postgres-data.tar.gz
│   ├── qdrant-storage.tar.gz
│   ├── redis-data.tar.gz
│   └── ...
└── migration_metadata.json
```

**Duration:** 10-60 minutes (depends on data size)

### Phase 2: Validation

Validates exported archives for integrity and completeness.

**Checks performed:**
- File existence
- Checksum verification (SHA256)
- Tar archive integrity
- Expected file patterns present

**Example validation patterns:**
- PostgreSQL: `pgdata`, `pg_wal`
- Qdrant: `collection`
- Redis: `appendonly.aof`
- MinIO: `.minio.sys`

### Phase 3: Import

Imports data to Kubernetes PersistentVolumeClaims.

**What happens:**
- Creates PVCs if they don't exist
- Waits for PVCs to be bound
- Creates temporary import pods
- Copies archives to pods
- Extracts archives to PVCs
- Verifies import success
- Cleans up temporary resources

**Duration:** 20-120 minutes (depends on data size and network)

### Phase 4: Rollback (if needed)

Restores Docker Compose environment.

**What happens:**
- Scales down Kubernetes deployments
- Preserves Docker volumes (data intact)
- Instructions to restart Docker Compose

## Pre-Migration Checklist

- [ ] Stop all Docker Compose services: `docker compose down`
- [ ] Verify Docker volumes exist: `docker volume ls`
- [ ] Ensure sufficient disk space (3x volume sizes recommended)
- [ ] Verify kubectl access: `kubectl cluster-info`
- [ ] Create namespace: `kubectl create namespace ai-platform`
- [ ] Configure storage class (if using specific provisioner)
- [ ] Backup critical data separately (optional but recommended)

## Post-Migration Steps

### 1. Verify Data in Kubernetes

```bash
# Check PVCs are bound
kubectl get pvc -n ai-platform

# Verify data in PostgreSQL
kubectl exec -it postgres-0 -n ai-platform -- psql -U ai_user -d ai_platform -c "\dt"

# Verify Qdrant collections
kubectl exec -it qdrant-0 -n ai-platform -- wget -q -O - http://localhost:6333/collections

# Check Redis data
kubectl exec -it redis-0 -n ai-platform -- redis-cli DBSIZE

# Verify MinIO buckets
kubectl port-forward -n ai-platform svc/minio 9001:9001
# Open http://localhost:9001
```

### 2. Deploy Applications

```bash
# Deploy with Helm
cd helm/ai-platform
helm install ai-platform . -n ai-platform

# Or apply manifests
kubectl apply -f helm/ai-platform/templates/ -n ai-platform
```

### 3. Verify Services

```bash
# Check all pods are running
kubectl get pods -n ai-platform

# Check service endpoints
kubectl get svc -n ai-platform

# Test API endpoint
kubectl port-forward -n ai-platform svc/api-server 8000:8000
curl http://localhost:8000/health
```

### 4. Update DNS/Ingress

Update your DNS records and ingress configurations to point to the Kubernetes services.

## Troubleshooting

### Export Issues

**Problem:** Volume doesn't exist
```bash
# List all volumes
docker volume ls

# Check volume name in docker-compose.yaml
grep "volumes:" -A 20 docker-compose.yaml
```

**Problem:** Export timeout
```bash
# Increase timeout in script (edit migrate_to_k8s.py)
# Line ~114: timeout=3600 -> timeout=7200
```

### Validation Issues

**Problem:** Checksum mismatch
```bash
# Re-export the specific volume
# Edit script to export single volume
# Or manually export with docker run
docker run --rm -v VOLUME_NAME:/source:ro -v $(pwd):/backup alpine tar czf /backup/volume.tar.gz -C /source .
```

**Problem:** Missing expected patterns
```bash
# Check archive contents
tar -tzf migration_work/exports/VOLUME_NAME.tar.gz | head -20

# Pattern might be in subdirectory - adjust validation_patterns in script
```

### Import Issues

**Problem:** PVC not binding
```bash
# Check storage class
kubectl get storageclass

# Check PVC status
kubectl describe pvc PVC_NAME -n ai-platform

# Check events
kubectl get events -n ai-platform --sort-by='.lastTimestamp'
```

**Problem:** Pod fails to start
```bash
# Check pod logs
kubectl logs POD_NAME -n ai-platform

# Check pod events
kubectl describe pod POD_NAME -n ai-platform

# Check node capacity
kubectl describe nodes
```

**Problem:** Copy to pod fails
```bash
# Check pod is running
kubectl get pod POD_NAME -n ai-platform

# Try manual copy
kubectl cp migration_work/exports/VOLUME.tar.gz ai-platform/POD_NAME:/tmp/data.tar.gz

# Check pod has write permissions
kubectl exec POD_NAME -n ai-platform -- df -h
```

### General Issues

**Problem:** Script hangs
```bash
# Check for blocking operations
ps aux | grep kubectl

# Check cluster connectivity
kubectl get nodes

# Interrupt and check logs
tail -f migration_*.log
```

**Problem:** Out of disk space
```bash
# Check available space
df -h

# Clean up Docker images/containers
docker system prune -a

# Clean up old migration attempts
rm -rf migration_work/
```

## Rollback Procedure

If migration fails or issues are discovered:

### 1. Automatic Rollback

```bash
python migrate_to_k8s.py rollback
```

This will:
- Scale down Kubernetes deployments
- Preserve Docker volumes
- Provide instructions to restart Docker Compose

### 2. Manual Rollback

```bash
# Scale down K8s deployments
kubectl scale deployment --all --replicas=0 -n ai-platform
kubectl scale statefulset --all --replicas=0 -n ai-platform

# Verify Docker volumes are intact
docker volume ls

# Restart Docker Compose
docker compose up -d

# Verify services
docker compose ps
curl http://localhost:8000/health
```

### 3. Full Restore from Backup

If Docker volumes are corrupted:

```bash
# Restore docker-compose.yaml
cp migration_work/backups/docker-compose.yaml ./

# Import volumes from exports (if needed)
for volume in postgres-data qdrant-storage redis-data; do
    docker volume create $volume
    docker run --rm \
        -v $volume:/restore \
        -v $(pwd)/migration_work/exports:/backup \
        alpine sh -c "cd /restore && tar xzf /backup/${volume}.tar.gz"
done

# Start services
docker compose up -d
```

## Migration Metadata

The script maintains state in `migration_metadata.json`:

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "phase": "import",
  "status": "completed",
  "volumes": {
    "postgres-data": {
      "archive": "migration_work/exports/postgres-data.tar.gz",
      "checksum": "abc123...",
      "size": 5368709120,
      "exported_at": "2024-01-15T10:35:00",
      "validated": true,
      "validated_at": "2024-01-15T10:45:00",
      "imported": true,
      "imported_at": "2024-01-15T11:00:00",
      "k8s_pvc": "postgres-data"
    }
  },
  "checksums": {
    "postgres-data": "abc123..."
  },
  "errors": []
}
```

## Best Practices

### Before Migration

1. **Perform a test migration** on a staging environment
2. **Stop application services** to ensure data consistency
3. **Create external backups** of critical data
4. **Document current state** (configurations, versions, etc.)
5. **Plan maintenance window** (allow 2-4 hours)

### During Migration

1. **Monitor disk space** continuously
2. **Watch for errors** in migration logs
3. **Keep Docker volumes** until migration is verified
4. **Don't delete exports** until Kubernetes is stable
5. **Document any issues** encountered

### After Migration

1. **Verify all data** is accessible
2. **Run application tests** to ensure functionality
3. **Monitor performance** for first 24-48 hours
4. **Keep Docker environment** available for 1 week
5. **Archive migration artifacts** for audit trail

## Performance Tuning

### For Large Volumes (>100GB)

```python
# Edit migrate_to_k8s.py

# Increase timeouts
timeout=7200  # 2 hours for export
timeout=7200  # 2 hours for import

# Use compression level (faster, larger files)
"tar", "czf", "--use-compress-program=pigz -1"
```

### For Slow Networks

```python
# Split large volumes into chunks
# Or use persistent volume snapshots if supported
# Or use direct volume cloning (CSI drivers)
```

### For Many Small Files

```python
# Use different compression
"tar", "cf", "--use-compress-program=pigz -9"  # Better compression

# Or disable compression for speed
"tar", "cf"  # No compression
```

## Security Considerations

1. **Credentials**: Exported archives contain sensitive data
2. **Access Control**: Restrict access to migration artifacts
3. **Encryption**: Consider encrypting exports at rest
4. **Cleanup**: Securely delete migration artifacts after success
5. **Audit**: Log all migration activities

## Support and Troubleshooting

### Log Files

- Migration log: `migration_TIMESTAMP.log`
- Kubernetes events: `kubectl get events -n ai-platform`
- Pod logs: `kubectl logs POD_NAME -n ai-platform`

### Common Log Locations

```bash
# Migration logs
ls -lt migration_*.log

# Kubernetes events
kubectl get events -n ai-platform --sort-by='.lastTimestamp' | tail -50

# Pod-specific logs
kubectl logs -l app=migration-import -n ai-platform --tail=100
```

### Getting Help

1. Check logs for specific error messages
2. Review this troubleshooting guide
3. Verify prerequisites are met
4. Test individual components separately
5. Consult Kubernetes cluster documentation

## Appendix

### A. Volume Mapping

| Docker Volume | K8s PVC | StatefulSet | Mount Path |
|---------------|---------|-------------|------------|
| postgres-data | postgres-data | postgres-0 | /var/lib/postgresql/data |
| qdrant-storage | qdrant-data | qdrant-0 | /qdrant/storage |
| redis-data | redis-data | redis-0 | /data |
| minio-data | minio-data | minio-0 | /data |
| neo4j-data | neo4j-data | neo4j-0 | /data |
| neo4j-logs | neo4j-logs | neo4j-0 | /logs |
| jaeger-data | jaeger-data | jaeger-0 | /badger |
| prometheus-data | prometheus-data | prometheus-0 | /prometheus |
| grafana-data | grafana-data | grafana-0 | /var/lib/grafana |

### B. Script Architecture

```
migrate_to_k8s.py
├── VolumeExporter
│   ├── export_volume()
│   ├── _volume_exists()
│   └── _calculate_checksum()
├── DataValidator
│   ├── validate_archive()
│   ├── _verify_tar_integrity()
│   └── _check_patterns()
├── KubernetesImporter
│   ├── import_to_pvc()
│   ├── _create_pvc()
│   ├── _create_import_pod()
│   ├── _wait_for_pod_running()
│   └── _verify_import()
└── MigrationOrchestrator
    ├── export_all()
    ├── validate_all()
    ├── import_all()
    ├── rollback()
    └── generate_report()
```

### C. Timeline Estimates

| Environment | Export | Validate | Import | Total |
|-------------|--------|----------|--------|-------|
| Small (<10GB) | 5-10 min | 2-5 min | 10-20 min | 20-35 min |
| Medium (10-50GB) | 15-30 min | 5-10 min | 30-60 min | 50-100 min |
| Large (50-200GB) | 30-60 min | 10-20 min | 60-120 min | 100-200 min |
| Extra Large (>200GB) | 1-2 hours | 20-30 min | 2-4 hours | 3-7 hours |

*Estimates assume good network and storage performance*

---

**Last Updated:** 2024-01-15  
**Version:** 1.0  
**Maintained By:** AI Platform Team
