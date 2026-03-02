# Learning Engine Service

Continuous learning system with LoRA fine-tuning, Fisher Information Matrix calculation, and Elastic Weight Consolidation (EWC) regularization.

## Features

- **LoRA Rank-16 Fine-tuning**: Efficient parameter-efficient fine-tuning using Low-Rank Adaptation
- **Fisher Information Matrix (FIM)**: Calculates parameter importance for current tasks
- **EWC Regularization (λ=100-1000)**: Prevents catastrophic forgetting during continual learning
- **Adapter Versioning**: Semantic versioning (v1.0, v1.1, ...) stored on MinIO
- **Hot-swap Integration**: Seamless adapter deployment to MAX Serve
- **Automated Scheduling**: Weekly training on interaction data
- **GPU Acceleration**: CUDA-optimized training pipeline

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Learning Engine Service                   │
│                        (Port 8003)                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   LoRA       │  │   Fisher     │  │   Storage    │     │
│  │   Trainer    │  │   Calculator │  │   Manager    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                  │                  │             │
│         │                  │                  │             │
│         ▼                  ▼                  ▼             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ EWC Loss     │  │ FIM Storage  │  │ MinIO S3     │     │
│  │ Computation  │  │ & Loading    │  │ Upload/DL    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
         │                         │
         ▼                         ▼
  ┌─────────────┐          ┌─────────────┐
  │ PostgreSQL  │          │   MinIO     │
  │  Feedback   │          │  Adapters   │
  └─────────────┘          └─────────────┘
```

## Configuration

### Environment Variables

```bash
# Model Configuration
MODEL_NAME=meta-llama/Llama-3.3-8B-Instruct
BASE_MODEL_PATH=/models/llama-3.3-8b-instruct-q4_k_m.gguf

# LoRA Configuration
LORA_RANK=16
LORA_ALPHA=32
LORA_DROPOUT=0.05
LORA_ENABLED=true
ACTIVE_LORA_ADAPTER=
LORA_CONTROL_BASE_URL=http://max-serve-llama:8080
LORA_RELOAD_ENDPOINT_PATH=/internal/lora/reload
LORA_ROLLBACK_ENDPOINT_PATH=/internal/lora/rollback
LORA_OPERATION_TIMEOUT_SECONDS=120

# EWC Configuration
EWC_LAMBDA=500.0  # Range: 100-1000

# Training Configuration
BATCH_SIZE=4
LEARNING_RATE=2e-4
NUM_TRAIN_EPOCHS=3

# Storage Configuration
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=lora-adapters

# Scheduling
AUTO_TRAIN_ENABLED=true
```

### YAML Configuration

See `configs/learning-engine.yaml` for detailed configuration options.

## API Endpoints

### Health Check
```bash
GET /health
```

Returns service health status and component states.

**Response:**
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

### LoRA Runtime Controls (hot-swap + rollback)
```bash
GET /lora/status
POST /lora/disable
POST /lora/enable
POST /lora/activate
POST /lora/rollback
```

These endpoints provide zero-downtime adapter activation via the LoRA control plane and fast rollback to the previous known-good adapter version.

### Trigger Training
```bash
POST /train
```

Start a new training job using feedback data.

### Trigger JSONL Training
```bash
POST /train/jsonl
```

Start base LoRA fine-tuning from a JSONL dataset with optional hyperparameter overrides.

**Request:**
```json
{
  "dataset_path": "data/train.jsonl",
  "learning_rate": 0.0002,
  "epochs": 3,
  "batch_size": 4
}
```

**Response:**
```json
{
  "status": "started",
  "message": "JSONL training job started with ID: train_jsonl_20250225_120000",
  "job_id": "train_jsonl_20250225_120000"
}
```


**Request:**
```json
{
  "days": 7,
  "ewc_lambda": 500.0,
  "force": false
}
```

**Response:**
```json
{
  "status": "started",
  "message": "Training job started with ID: train_20250225_120000",
  "job_id": "train_20250225_120000"
}
```

### Calculate Fisher Matrix
```bash
POST /fisher/calculate
```

Calculate Fisher Information Matrix for EWC regularization.

**Request:**
```json
{
  "adapter_version": "v1.0",
  "num_samples": 1000
}
```

**Response:**
```json
{
  "status": "started",
  "message": "Fisher calculation started with version: fisher_20250225_120000",
  "fisher_version": "fisher_20250225_120000"
}
```

### List Adapters
```bash
GET /adapters
```

List all available LoRA adapters.

**Response:**
```json
{
  "adapters": [
    {
      "version": "v1.0",
      "job_id": "train_20250225_120000",
      "samples": 1500,
      "train_loss": 0.3245,
      "timestamp": "2025-02-25T12:00:00"
    }
  ],
  "total": 1
}
```

### Get Adapter Info
```bash
GET /adapters/{version}
```

Get detailed information about a specific adapter.

### Deploy Adapter
```bash
POST /adapters/{version}/deploy
```

Deploy an adapter to MAX Serve (hot-swap).

**Response:**
```json
{
  "status": "deployed",
  "message": "Adapter v1.0 deployed successfully",
  "version": "v1.0",
  "path": "/tmp/adapters/v1.0",
  "from_version": "v0.9",
  "duration_ms": 1342,
  "known_good_adapter_version": "v0.9"
}
```

### Training Status
```bash
GET /training/status
```

Get current training job status.

### Metrics
```bash
GET /metrics
```

Get training metrics and statistics.

## Usage

### Starting the Service

With Docker:
```bash
docker compose up learning-engine
```

Standalone:
```bash
python learning_engine_service.py
```

### CLI Tool

The CLI provides convenient access to all service functions:

```bash
# Check health
python learning_engine_cli.py health

# Trigger training
python learning_engine_cli.py train --days 7 --ewc-lambda 500

# Calculate Fisher matrix
python learning_engine_cli.py fisher --num-samples 1000

# List adapters
python learning_engine_cli.py list-adapters

# Deploy adapter
python learning_engine_cli.py deploy v1.0

# Get status
python learning_engine_cli.py status

# Get metrics
python learning_engine_cli.py metrics
```

### Python API

```python
import httpx
import asyncio

async def trigger_training():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8003/train",
            json={"days": 7, "ewc_lambda": 500.0}
        )
        return response.json()

result = asyncio.run(trigger_training())
print(f"Training job: {result['job_id']}")
```

## LoRA Fine-tuning Details

### LoRA Configuration

- **Rank**: 16 (balances efficiency and expressiveness)
- **Alpha**: 32 (scaling factor, typically 2×rank)
- **Dropout**: 0.05 (regularization)
- **Target Modules**: q_proj, v_proj, k_proj, o_proj (attention layers)

### Training Process

1. **Data Loading**: Extracts feedback from PostgreSQL
   - Positive feedback (👍): 2.0× weight
   - Negative feedback (👎): 0.5× weight

2. **Fisher Calculation**: Computes parameter importance
   - Uses 1000 samples from current task
   - Calculates diagonal approximation of FIM
   - Stored for EWC regularization

3. **LoRA Training**: Fine-tunes adapter weights
   - Base model frozen
   - Only LoRA parameters trained
   - Gradient accumulation for larger effective batch size

4. **EWC Regularization**: Prevents forgetting
   ```
   Loss = Task_Loss + (λ/2) * Σ F_i * (θ_i - θ*_i)^2
   ```
   - λ: 100-1000 (configurable)
   - F_i: Fisher importance values
   - θ*_i: Old parameter values

5. **Versioning**: Increments version (v1.0 → v1.1)

6. **Storage**: Uploads to MinIO with metadata

## EWC Regularization

Elastic Weight Consolidation prevents catastrophic forgetting by:

1. Identifying important parameters using Fisher Information
2. Penalizing large changes to important parameters
3. Allowing flexibility in unimportant parameters

### Lambda Values

- **λ=100**: Light regularization (more plasticity)
- **λ=500**: Balanced (default)
- **λ=1000**: Strong regularization (more stability)

## Adapter Versioning

Adapters use semantic versioning:

- **v1.0**: Initial version
- **v1.1, v1.2, ...**: Minor increments (weekly updates)
- **v2.0**: Major version (significant changes)

Each version includes:
- LoRA weights (adapter.tar.gz)
- Training metadata (metadata.json)
- Performance metrics
- Timestamp

## Storage on MinIO

Adapters are stored in S3-compatible MinIO:

```
lora-adapters/
├── adapters/
│   ├── v1.0/
│   │   ├── adapter.tar.gz
│   │   └── metadata.json
│   ├── v1.1/
│   │   ├── adapter.tar.gz
│   │   └── metadata.json
│   └── ...
└── fisher/
    ├── fisher_latest.pt
    └── fisher_latest_metadata.json
```

## Hot-swap with MAX Serve

Adapters can be deployed to MAX Serve without downtime:

1. Download adapter from MinIO
2. Signal MAX Serve to load new adapter
3. MAX Serve switches to new weights
4. Previous adapter unloaded

## Scheduling

Automatic training runs on schedule:

- **Default**: Every Monday at 2 AM
- **Cron Expression**: `0 2 * * 1`
- **Configurable**: Via `train_schedule_cron` config

Requirements for auto-training:
- Minimum 100 samples (configurable)
- Successful Fisher matrix calculation
- Available GPU resources

## Performance

### Training Time

- **Small dataset** (100-500 samples): 5-15 minutes
- **Medium dataset** (500-2000 samples): 15-45 minutes
- **Large dataset** (2000+ samples): 45-120 minutes

*Times vary based on GPU, sequence length, and batch size*

### Memory Usage

- **Base Model**: ~8GB VRAM (Llama 3.3 8B FP16)
- **LoRA Adapters**: ~100MB per adapter
- **Training Peak**: ~12GB VRAM
- **Fisher Matrix**: ~500MB disk space

### Adapter Size

- **LoRA Rank 16**: ~80-100MB per adapter
- **Compressed (tar.gz)**: ~30-40MB

## Monitoring

### Metrics

- Training loss
- EWC loss component
- Number of samples
- Training duration
- GPU utilization

### Logs

Service logs include:
- Training progress
- Fisher calculation status
- Adapter upload/download
- Scheduler events
- Error traces

## Troubleshooting

### Training Fails

**Issue**: Not enough samples
```
Solution: Reduce min_samples_for_training or use --force flag
```

**Issue**: Out of GPU memory
```
Solution: Reduce batch_size or max_seq_length
```

### Fisher Calculation Fails

**Issue**: Model not loaded
```
Solution: Ensure base model exists at BASE_MODEL_PATH
```

### Storage Errors

**Issue**: MinIO connection failed
```
Solution: Check MINIO_ENDPOINT and credentials
```

### Scheduler Not Running

**Issue**: AUTO_TRAIN_ENABLED=false
```
Solution: Set AUTO_TRAIN_ENABLED=true in environment
```

## Testing

Run the test suite:

```bash
python test_learning_engine.py
```

Tests include:
- Health checks
- Training trigger
- Fisher calculation
- Adapter management
- Storage operations

## Integration with MAX Serve

The learning engine integrates with MAX Serve for:

1. **Model Loading**: Loads base model for fine-tuning
2. **Adapter Deployment**: Hot-swaps adapters at runtime
3. **Inference**: Serves requests with active adapter

Future enhancements:
- Automatic A/B testing of adapter versions
- Gradual rollout of new adapters
- Performance comparison between versions

## Best Practices

1. **Regular Training**: Schedule weekly updates to capture user feedback
2. **Monitor Metrics**: Track training loss and sample quality
3. **Version Control**: Keep at least 3-5 recent adapter versions
4. **EWC Lambda Tuning**: Start with λ=500, adjust based on forgetting/plasticity balance
5. **Fisher Recalculation**: Recalculate Fisher after major dataset changes
6. **Storage Cleanup**: Periodically archive old adapter versions

## Security

- Use secure credentials for MinIO access
- Limit API access with authentication (future)
- Validate training data inputs
- Monitor resource usage to prevent abuse
- Regular security updates for dependencies

## Future Enhancements

- [ ] Multi-task learning with task-specific adapters
- [ ] Online learning with streaming data
- [ ] Adapter merging for consolidated models
- [ ] Automated hyperparameter tuning
- [ ] Integration with experiment tracking (MLflow/Weights & Biases)
- [ ] Support for multiple base models
- [ ] Distributed training across multiple GPUs

## References

- **LoRA**: [LoRA: Low-Rank Adaptation of Large Language Models](https://arxiv.org/abs/2106.09685)
- **EWC**: [Overcoming catastrophic forgetting in neural networks](https://arxiv.org/abs/1612.00796)
- **Fisher Information**: [Natural Gradient Works Efficiently in Learning](https://www.mitpressjournals.org/doi/abs/10.1162/089976698300017746)

## License

See repository LICENSE file.
