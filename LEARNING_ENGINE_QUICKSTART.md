# Learning Engine Quickstart

Get started with continuous learning in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- NVIDIA GPU with CUDA support
- At least 16GB RAM
- PostgreSQL with feedback data

## Quick Start

### 1. Start the Service

```bash
# Start learning engine with dependencies
docker compose up -d learning-engine postgres minio
```

### 2. Check Health

```bash
curl http://localhost:8003/health
```

Expected output:
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

### 3. Trigger First Training

```bash
# Using CLI
python learning_engine_cli.py train --days 7 --force

# Or using curl
curl -X POST http://localhost:8003/train \
  -H "Content-Type: application/json" \
  -d '{"days": 7, "ewc_lambda": 500.0, "force": true}'
```

### 4. Monitor Progress

```bash
# Check training status
python learning_engine_cli.py status

# View metrics
python learning_engine_cli.py metrics
```

### 5. List Adapters

```bash
python learning_engine_cli.py list-adapters
```

### 6. Deploy Adapter

```bash
# Deploy latest version
python learning_engine_cli.py deploy v1.0
```

## Configuration

### Basic Configuration

Edit `configs/learning-engine.yaml`:

```yaml
lora:
  rank: 16
  alpha: 32

ewc:
  lambda_default: 500.0

training:
  batch_size: 4
  num_train_epochs: 3

scheduler:
  enabled: true
  cron: "0 2 * * 1"  # Every Monday at 2 AM
```

### Environment Variables

Create `.env.learning` file:

```bash
# Model
MODEL_NAME=meta-llama/Llama-3.3-8B-Instruct
LORA_RANK=16
EWC_LAMBDA=500.0

# Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123

# Scheduling
AUTO_TRAIN_ENABLED=true
```

## Common Tasks

### Manual Training

```bash
# Train on last 7 days of feedback
python learning_engine_cli.py train --days 7

# Train with custom EWC lambda
python learning_engine_cli.py train --days 14 --ewc-lambda 1000

# Force training even with low samples
python learning_engine_cli.py train --force
```

### Fisher Matrix Calculation

```bash
# Calculate Fisher for current model
python learning_engine_cli.py fisher --num-samples 1000

# Calculate for specific adapter
python learning_engine_cli.py fisher --adapter v1.0 --num-samples 500
```

### Adapter Management

```bash
# List all adapters
python learning_engine_cli.py list-adapters

# Get adapter details
python learning_engine_cli.py adapter-info v1.0

# Deploy adapter
python learning_engine_cli.py deploy v1.0
```

### Monitoring

```bash
# Service health
python learning_engine_cli.py health

# Training status
python learning_engine_cli.py status

# Metrics
python learning_engine_cli.py metrics
```

## Testing

Run the test suite:

```bash
python test_learning_engine.py
```

## API Examples

### Python

```python
import httpx
import asyncio

async def main():
    async with httpx.AsyncClient() as client:
        # Trigger training
        response = await client.post(
            "http://localhost:8003/train",
            json={"days": 7, "ewc_lambda": 500.0}
        )
        print(response.json())

asyncio.run(main())
```

### JavaScript

```javascript
// Trigger training
fetch('http://localhost:8003/train', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({days: 7, ewc_lambda: 500.0})
})
.then(r => r.json())
.then(data => console.log(data));
```

### cURL

```bash
# Trigger training
curl -X POST http://localhost:8003/train \
  -H "Content-Type: application/json" \
  -d '{"days": 7, "ewc_lambda": 500.0, "force": false}'

# List adapters
curl http://localhost:8003/adapters

# Deploy adapter
curl -X POST http://localhost:8003/adapters/v1.0/deploy
```

## Automated Schedule

The service automatically trains weekly by default:

- **Schedule**: Every Monday at 2 AM
- **Data**: Last 7 days of feedback
- **Minimum**: 100 samples required

To disable automatic training:

```bash
# Set in docker-compose.yaml
environment:
  - AUTO_TRAIN_ENABLED=false
```

## Viewing Logs

```bash
# Real-time logs
docker compose logs -f learning-engine

# Last 100 lines
docker compose logs --tail=100 learning-engine

# Search logs
docker compose logs learning-engine | grep "Training"
```

## Storage

Adapters are stored in MinIO:

```bash
# Access MinIO Console
# URL: http://localhost:9001
# User: minioadmin
# Password: minioadmin123
```

Navigate to `lora-adapters` bucket to view adapters.

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs learning-engine

# Verify dependencies
docker compose ps postgres minio
```

### Training Fails

```bash
# Check sample count
python learning_engine_cli.py status

# Use force flag
python learning_engine_cli.py train --force
```

### Out of Memory

Edit `configs/learning-engine.yaml`:

```yaml
training:
  batch_size: 2  # Reduce from 4
  max_seq_length: 1024  # Reduce from 2048
```

### Connection Errors

```bash
# Verify services are running
docker compose ps

# Check network
docker network inspect ai-platform-net
```

## Performance Tips

1. **Batch Size**: Start with 4, reduce if OOM errors
2. **Sequence Length**: Limit to 2048 for most use cases
3. **EWC Lambda**: 
   - Low (100): Fast adaptation, more forgetting
   - Medium (500): Balanced (recommended)
   - High (1000): Slow adaptation, less forgetting
4. **Training Frequency**: Weekly is recommended
5. **Sample Size**: Minimum 100, optimal 500-2000

## Next Steps

1. Review [LEARNING_ENGINE_README.md](LEARNING_ENGINE_README.md) for detailed documentation
2. Explore API endpoints with Postman/Insomnia
3. Integrate with your application
4. Set up automated training schedule
5. Monitor adapter performance
6. Tune hyperparameters based on metrics

## Support

- Check logs for errors
- Review configuration files
- Verify GPU availability: `nvidia-smi`
- Test with CLI tool first
- Consult README for detailed troubleshooting

## Example Workflow

```bash
# 1. Start service
docker compose up -d learning-engine

# 2. Wait for initialization
sleep 30

# 3. Check health
python learning_engine_cli.py health

# 4. Calculate initial Fisher matrix
python learning_engine_cli.py fisher --num-samples 1000

# 5. Trigger training
python learning_engine_cli.py train --days 7

# 6. Wait for training (monitor with status)
python learning_engine_cli.py status

# 7. List available adapters
python learning_engine_cli.py list-adapters

# 8. Deploy new adapter
python learning_engine_cli.py deploy v1.0

# 9. Verify deployment
curl http://localhost:8003/adapters/v1.0
```

## Maintenance

### Weekly Tasks

- Review training metrics
- Check adapter performance
- Monitor storage usage
- Verify automatic training runs

### Monthly Tasks

- Archive old adapters
- Update base model if needed
- Tune hyperparameters based on performance
- Review and optimize EWC lambda

### Quarterly Tasks

- Major version updates
- Comprehensive performance evaluation
- Infrastructure scaling assessment
- Security updates

---

**Ready to start learning!** 🚀
