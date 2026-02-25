# Learning Engine Deployment Checklist

Step-by-step deployment guide for the learning engine service.

## Pre-Deployment Checklist

### System Requirements

- [ ] **Hardware**
  - [ ] NVIDIA GPU with 12GB+ VRAM
  - [ ] 16GB+ RAM
  - [ ] 100GB+ free disk space
  - [ ] 4+ CPU cores

- [ ] **Software**
  - [ ] Docker Engine 20.10+
  - [ ] Docker Compose 2.0+
  - [ ] NVIDIA Docker runtime
  - [ ] Python 3.10+ (for CLI)

- [ ] **Services**
  - [ ] PostgreSQL 15 with feedback table
  - [ ] MinIO running and accessible
  - [ ] MAX Serve (optional, for deployment)

### Verification Steps

```bash
# Check GPU
nvidia-smi

# Check Docker
docker --version
docker compose version

# Check NVIDIA Docker
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# Check disk space
df -h
```

## Configuration Steps

### 1. Environment Configuration

```bash
# Copy environment template
cp .env.learning.example .env.learning

# Edit configuration
nano .env.learning
```

**Key settings to review**:
- `MODEL_NAME` - Ensure correct model identifier
- `EWC_LAMBDA` - Start with 500.0
- `MINIO_ENDPOINT` - Verify MinIO connection
- `POSTGRES_HOST` - Verify database connection
- `AUTO_TRAIN_ENABLED` - Set to true for automatic training

### 2. Model Setup

```bash
# Ensure model file exists
ls -lh models/llama-3.3-8b-instruct-q4_k_m.gguf

# If missing, download
make download
# or
./download_model.sh
```

### 3. Directory Structure

```bash
# Create required directories
mkdir -p lora_adapters
mkdir -p lora_checkpoints
mkdir -p fisher_matrices

# Set permissions
chmod 755 lora_adapters lora_checkpoints fisher_matrices
```

### 4. MinIO Bucket Setup

```bash
# Access MinIO console
# URL: http://localhost:9001
# User: minioadmin
# Password: minioadmin123

# Create bucket via CLI (alternative)
docker run --rm --network ai-platform-net \
  -e MC_HOST_minio=http://minioadmin:minioadmin123@minio:9000 \
  minio/mc mb minio/lora-adapters
```

### 5. Database Verification

```bash
# Check feedback table exists
docker exec -it postgres psql -U ai_user -d ai_platform -c "\d feedback"

# Verify feedback data
docker exec -it postgres psql -U ai_user -d ai_platform -c \
  "SELECT COUNT(*) FROM feedback WHERE feedback_type IN ('thumbs_up', 'thumbs_down');"
```

## Deployment

### Build and Start

```bash
# Option 1: Using Make (recommended)
make learning

# Option 2: Using Docker Compose
docker compose build learning-engine
docker compose up -d learning-engine postgres minio

# Option 3: Full stack
docker compose up -d
```

### Verify Deployment

```bash
# Check service is running
docker compose ps learning-engine

# Check logs
docker compose logs learning-engine

# Health check
curl http://localhost:8003/health

# Or using Make
make learning-status
```

### Expected Output

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "components": {
    "trainer": "healthy",
    "fisher_calculator": "healthy",
    "storage": "healthy",
    "scheduler": "healthy"
  }
}
```

## Initial Setup

### 1. Calculate Initial Fisher Matrix

```bash
# Using CLI
python learning_engine_cli.py fisher --num-samples 1000

# Using API
curl -X POST http://localhost:8003/fisher/calculate \
  -H "Content-Type: application/json" \
  -d '{"num_samples": 1000}'
```

### 2. Run First Training

```bash
# Using CLI (forced to bypass sample check)
python learning_engine_cli.py train --days 7 --force

# Using Make
make learning-train

# Using API
curl -X POST http://localhost:8003/train \
  -H "Content-Type: application/json" \
  -d '{"days": 7, "force": true, "ewc_lambda": 500.0}'
```

### 3. Monitor Training

```bash
# Watch logs
make learning-logs

# Check status
python learning_engine_cli.py status

# Check metrics
python learning_engine_cli.py metrics
```

### 4. Verify Adapter Creation

```bash
# List adapters
python learning_engine_cli.py list-adapters

# Check MinIO
# Navigate to http://localhost:9001
# Browse lora-adapters bucket
```

## Post-Deployment

### Smoke Tests

```bash
# Run full test suite
python test_learning_engine.py

# Or using Make
make learning-test
```

### Integration Tests

```bash
# Test training endpoint
curl -X POST http://localhost:8003/train \
  -H "Content-Type: application/json" \
  -d '{"days": 7, "ewc_lambda": 500.0}'

# Test adapter listing
curl http://localhost:8003/adapters

# Test health endpoint
curl http://localhost:8003/health
```

### Performance Validation

```bash
# Monitor GPU usage
watch -n 1 nvidia-smi

# Monitor service resources
docker stats learning-engine

# Check storage usage
du -sh lora_adapters/ fisher_matrices/
```

## Monitoring Setup

### Log Collection

```bash
# Enable persistent logging
docker compose logs -f learning-engine > logs/learning-engine.log 2>&1 &

# Set up log rotation (optional)
cat > /etc/logrotate.d/learning-engine <<EOF
/path/to/logs/learning-engine.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF
```

### Metrics Dashboard

```bash
# View real-time metrics
watch -n 5 'curl -s http://localhost:8003/metrics | python -m json.tool'

# Check training status
watch -n 10 'curl -s http://localhost:8003/training/status | python -m json.tool'
```

### Alerting (Optional)

Set up alerts for:
- Training failures
- Low disk space
- High GPU memory usage
- Service downtime

## Scheduler Verification

### Check Schedule

```bash
# Verify scheduler is running
curl http://localhost:8003/health | jq '.components.scheduler'

# Expected: "healthy" or "not_running" (if AUTO_TRAIN_ENABLED=false)
```

### Test Scheduled Training

```bash
# Check logs for scheduler activity
docker compose logs learning-engine | grep -i "scheduled"

# Manually trigger to test
python learning_engine_cli.py train --days 7
```

### Modify Schedule (if needed)

```bash
# Edit docker-compose.yaml
nano docker-compose.yaml

# Update TRAIN_SCHEDULE_CRON environment variable
# Example: "0 3 * * 0" for Sunday 3 AM

# Restart service
docker compose restart learning-engine
```

## Security Hardening

### 1. Change Default Credentials

```bash
# Update MinIO credentials
# In docker-compose.yaml or .env:
MINIO_ROOT_USER=<strong-username>
MINIO_ROOT_PASSWORD=<strong-password>

# Update learning engine environment
MINIO_ACCESS_KEY=<strong-username>
MINIO_SECRET_KEY=<strong-password>
```

### 2. Enable TLS (Production)

```bash
# Configure MinIO with TLS
MINIO_SECURE=true

# Update endpoint
MINIO_ENDPOINT=minio.yourdomain.com:443
```

### 3. Network Isolation

```bash
# Use internal networks for services
# Expose only necessary ports
# Consider using reverse proxy for API
```

### 4. Access Control

```bash
# Restrict API access (future)
# Implement authentication
# Use API keys
# Set up rate limiting
```

## Backup Strategy

### Adapter Backups

```bash
# Backup MinIO data
docker exec minio mc mirror /data /backup

# Export adapters locally
python learning_engine_cli.py list-adapters
# Download important versions
```

### Fisher Matrix Backups

```bash
# Backup Fisher matrices
tar -czf fisher_backup_$(date +%Y%m%d).tar.gz fisher_matrices/

# Store securely
mv fisher_backup_*.tar.gz /backup/location/
```

### Configuration Backups

```bash
# Backup configurations
cp docker-compose.yaml docker-compose.yaml.backup
cp .env.learning .env.learning.backup
cp configs/learning-engine.yaml configs/learning-engine.yaml.backup
```

## Disaster Recovery

### Service Recovery

```bash
# Stop service
docker compose stop learning-engine

# Remove container
docker compose rm -f learning-engine

# Rebuild and restart
docker compose build learning-engine
docker compose up -d learning-engine

# Verify
curl http://localhost:8003/health
```

### Data Recovery

```bash
# Restore MinIO data
docker exec minio mc mirror /backup /data

# Restore Fisher matrices
tar -xzf fisher_backup_*.tar.gz -C fisher_matrices/

# Restart service
docker compose restart learning-engine
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs learning-engine

# Common issues:
# - GPU not available
nvidia-smi

# - Dependencies not ready
docker compose ps postgres minio

# - Port conflict
lsof -i :8003
```

### Training Fails

```bash
# Check sample count
curl http://localhost:8003/training/status

# Verify database connection
docker exec -it postgres psql -U ai_user -d ai_platform -c "SELECT COUNT(*) FROM feedback;"

# Check GPU memory
nvidia-smi

# Reduce batch size if OOM
# Edit configs/learning-engine.yaml
batch_size: 2  # Reduce from 4
```

### Storage Issues

```bash
# Check MinIO connection
docker exec learning-engine curl -I http://minio:9000/minio/health/live

# Verify bucket exists
docker exec minio mc ls minio/

# Create bucket if missing
docker exec minio mc mb minio/lora-adapters
```

### Performance Issues

```bash
# Monitor resources
docker stats learning-engine

# Check GPU utilization
nvidia-smi dmon

# Tune hyperparameters
# Edit configs/learning-engine.yaml:
# - Reduce batch_size
# - Reduce max_seq_length
# - Adjust num_train_epochs
```

## Maintenance

### Weekly Tasks

- [ ] Review training logs
- [ ] Check adapter creation
- [ ] Verify scheduled training runs
- [ ] Monitor storage usage
- [ ] Review metrics

### Monthly Tasks

- [ ] Performance evaluation
- [ ] Hyperparameter tuning
- [ ] Archive old adapters
- [ ] Update dependencies
- [ ] Security updates

### Quarterly Tasks

- [ ] Major version updates
- [ ] Infrastructure scaling review
- [ ] Comprehensive testing
- [ ] Documentation updates
- [ ] Disaster recovery drill

## Rollback Procedure

### Service Rollback

```bash
# Stop current version
docker compose stop learning-engine

# Checkout previous version
git checkout <previous-tag>

# Rebuild and restart
docker compose build learning-engine
docker compose up -d learning-engine
```

### Adapter Rollback

```bash
# Deploy previous adapter version
python learning_engine_cli.py deploy v1.0  # Replace with desired version

# Verify deployment
curl http://localhost:8003/adapters/v1.0
```

## Production Checklist

Before going to production:

- [ ] All tests passing
- [ ] Documentation reviewed
- [ ] Credentials changed from defaults
- [ ] Backup strategy implemented
- [ ] Monitoring set up
- [ ] Alerting configured
- [ ] Disaster recovery tested
- [ ] Security hardening applied
- [ ] Performance benchmarked
- [ ] Rollback procedure documented

## Support

### Getting Help

1. Check logs: `make learning-logs`
2. Review documentation: `LEARNING_ENGINE_README.md`
3. Run tests: `make learning-test`
4. Check health: `curl http://localhost:8003/health`

### Common Commands

```bash
# Quick diagnostics
make learning-status
python learning_engine_cli.py health
docker compose ps
nvidia-smi

# Logs
make learning-logs
docker compose logs learning-engine --tail=100

# Restart
docker compose restart learning-engine

# Full reset
docker compose down
make learning
```

## Deployment Complete

Once all steps are completed:

✅ Service deployed and healthy
✅ Initial Fisher matrix calculated
✅ First training completed
✅ Adapters versioned and stored
✅ Monitoring in place
✅ Backups configured
✅ Documentation reviewed

**Your learning engine is ready for continuous learning!** 🚀
