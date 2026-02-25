# Docker to Kubernetes Migration - Quick Start

Fast-track guide for migrating AI Platform from Docker Compose to Kubernetes.

## Prerequisites ✓

```bash
# Run pre-flight check
chmod +x preflight_check.sh
./preflight_check.sh
```

## Migration Steps

### 1. Prepare Environment

```bash
# Stop Docker Compose services
docker compose down

# Create namespace
kubectl create namespace ai-platform

# Verify connection
kubectl cluster-info
docker volume ls
```

### 2. Run Migration

**Option A: Full Automated Migration (Recommended)**

```bash
# Complete migration in one command
python migrate_to_k8s.py full
```

**Option B: Step-by-Step Migration**

```bash
# Step 1: Export volumes
python migrate_to_k8s.py export

# Step 2: Validate exports
python migrate_to_k8s.py validate

# Step 3: Import to Kubernetes
python migrate_to_k8s.py import

# Check status
python migrate_to_k8s.py report
```

### 3. Deploy Applications

```bash
# Deploy with Helm
cd helm/ai-platform
helm install ai-platform . -n ai-platform

# Wait for pods
kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=database -n ai-platform --timeout=300s
```

### 4. Verify Migration

```bash
# Run verification script
chmod +x verify_migration.sh
./verify_migration.sh

# Check PVCs
kubectl get pvc -n ai-platform

# Check pods
kubectl get pods -n ai-platform
```

## Rollback (if needed)

```bash
# Automated rollback
chmod +x rollback_migration.sh
./rollback_migration.sh

# Or use Python script
python migrate_to_k8s.py rollback
```

## Quick Commands

```bash
# Check migration status
python migrate_to_k8s.py report

# View logs
tail -f migration_*.log

# Check Kubernetes events
kubectl get events -n ai-platform --sort-by='.lastTimestamp'

# Port forward services
kubectl port-forward -n ai-platform svc/api-server 8000:8000
kubectl port-forward -n ai-platform svc/grafana 3000:3000
```

## Common Issues

### Export fails
```bash
# Check Docker daemon
docker info

# Check volume exists
docker volume inspect VOLUME_NAME
```

### Import fails
```bash
# Check PVC status
kubectl describe pvc PVC_NAME -n ai-platform

# Check storage class
kubectl get storageclass
```

### Pods not starting
```bash
# Check logs
kubectl logs POD_NAME -n ai-platform

# Check events
kubectl describe pod POD_NAME -n ai-platform
```

## Timeline

- **Small env (<10GB)**: 20-35 minutes
- **Medium env (10-50GB)**: 50-100 minutes  
- **Large env (50-200GB)**: 100-200 minutes
- **XL env (>200GB)**: 3-7 hours

## Support

See detailed guide: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)

---

**Quick Reference Card**

| Phase | Command | Time |
|-------|---------|------|
| Pre-check | `./preflight_check.sh` | 2 min |
| Export | `python migrate_to_k8s.py export` | 15-60 min |
| Validate | `python migrate_to_k8s.py validate` | 5-20 min |
| Import | `python migrate_to_k8s.py import` | 30-120 min |
| Verify | `./verify_migration.sh` | 2 min |
| Rollback | `./rollback_migration.sh` | 10 min |
