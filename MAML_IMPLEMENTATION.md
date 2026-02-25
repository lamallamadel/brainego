# MAML Meta-Learning Implementation

## Overview

This implementation provides a complete MAML (Model-Agnostic Meta-Learning) pipeline for fast adaptation across projects and tasks. The system learns meta-weights that enable rapid adaptation to new tasks with minimal data, targeting **<10 steps to reach 80% accuracy**.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MAML Meta-Learning Pipeline                │
└──────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐   ┌────────▼────────┐   ┌────▼──────────┐
│ Task         │   │ Replay Buffer   │   │ Meta-Weights  │
│ Extractor    │   │ (3x Failed)     │   │ Storage       │
└───────┬──────┘   └────────┬────────┘   └────┬──────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                    ┌───────▼────────┐
                    │  MAML Learner  │
                    │  - Inner Loop  │
                    │  - Outer Loop  │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │ Adaptation     │
                    │ Metrics        │
                    │ Tracker        │
                    └────────────────┘
```

## Components

### 1. MAML Learner (`learning_engine/maml.py`)

Core MAML algorithm implementation with two-loop structure:

**Inner Loop (Task Adaptation):**
- Fast adaptation to specific tasks using few gradient steps
- Default: 5 steps with learning rate 1e-3
- Uses support set for training

**Outer Loop (Meta-Optimization):**
- Optimizes meta-parameters across all tasks
- Default: 100 steps with learning rate 1e-4
- Uses query set for evaluation

**Features:**
- LoRA-based parameter-efficient fine-tuning
- Support for multiple tasks per meta-batch
- Automatic checkpoint saving/loading
- Adaptation history tracking

### 2. Task Extractor (`learning_engine/task_extractor.py`)

Extracts and organizes feedback data into project-specific tasks:

**Extraction Strategies:**
- **Project-based**: Group by project identifier
- **Intent-based**: Group by task intent/type
- **Temporal**: Group by time windows (weekly buckets)
- **Mixed**: Combine multiple strategies

**Features:**
- Configurable minimum samples per task (default: 20)
- Failed plan extraction for replay buffer
- Project statistics and analytics
- Flexible time period selection

### 3. Replay Buffer (`learning_engine/replay_buffer.py`)

Weighted replay buffer with 3x multiplier for failed plans:

**Features:**
- Failed plans receive 3x weight (configurable)
- Separate buffer for failed plans
- Weighted sampling for training
- Priority-based variant (PrioritizedReplayBuffer)
- Buffer balancing and statistics

**Weight Distribution:**
- Failed plans (rating=-1): 3.0x weight
- Positive feedback (rating=1): 1.0x weight
- Other negative: 0.5x weight

### 4. Meta-Weights Storage (`learning_engine/meta_storage.py`)

MinIO-based storage with versioning:

**Features:**
- Versioned meta-weights storage
- Metadata tracking (performance, tasks, timestamps)
- Version comparison and rollback
- Automatic backup functionality
- Storage statistics

**Version Format:**
```
meta-weights/
  ├── maml_20240115_020000/
  │   ├── meta_weights.pt
  │   └── metadata.json
  └── maml_20240201_020000/
      ├── meta_weights.pt
      └── metadata.json
```

### 5. Adaptation Metrics Tracker (`learning_engine/adaptation_metrics.py`)

PostgreSQL-based metrics tracking:

**Tracked Metrics:**
- Steps to target accuracy (target: <10 steps)
- Final accuracy achieved (target: ≥80%)
- Adaptation loss curve
- Task-specific performance
- Success rate

**Database Tables:**
- `maml_adaptation_metrics`: Per-task adaptation results
- `maml_meta_training_metrics`: Meta-training results

### 6. Monthly Scheduler (`learning_engine/maml_scheduler.py`)

CronJob scheduler for periodic meta-training:

**Default Schedule:**
- Monthly: 1st day of month at 2 AM
- Cron format: `0 2 1 * *`

**Features:**
- Async scheduling with croniter
- Manual trigger support
- Next run time calculation
- Graceful shutdown

## API Endpoints

### MAML Service (Port 8005)

#### Health Check
```
GET /health
```

#### Trigger Meta-Training
```
POST /meta-train
Body: {
  "days": 30,
  "task_strategy": "mixed",
  "num_outer_steps": 100,
  "force": false
}
```

#### Fast Adaptation
```
POST /adapt
Body: {
  "project": "project_name",
  "days": 7,
  "target_accuracy": 0.80,
  "max_steps": 10
}
```

#### List Meta-Weights Versions
```
GET /meta-weights/versions
```

#### Adaptation Metrics
```
GET /metrics/adaptation?days=30&project=optional
```

#### Project Performance
```
GET /metrics/projects?days=30
```

#### Scheduler Info
```
GET /scheduler/info
```

#### Manual Trigger Scheduler
```
POST /scheduler/trigger
```

#### Replay Buffer Stats
```
GET /replay-buffer/stats
```

## Configuration

### Environment Variables

```bash
# Service
MAML_SERVICE_HOST=0.0.0.0
MAML_SERVICE_PORT=8005

# Model
MODEL_NAME=meta-llama/Llama-3.3-8B-Instruct
LORA_RANK=16
LORA_ALPHA=32
LORA_DROPOUT=0.05

# MAML Hyperparameters
MAML_INNER_LR=1e-3          # Inner loop learning rate
MAML_OUTER_LR=1e-4          # Outer loop learning rate
MAML_INNER_STEPS=5          # Adaptation steps per task
MAML_OUTER_STEPS=100        # Meta-optimization steps

# Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password

# Scheduling
MAML_SCHEDULE_ENABLED=true
MAML_CRON_SCHEDULE=0 2 1 * *
```

## Usage Examples

### 1. Manual Meta-Training

```python
import httpx

# Trigger meta-training
response = httpx.post("http://localhost:8005/meta-train", json={
    "days": 30,
    "task_strategy": "mixed",
    "num_outer_steps": 100
})
print(response.json())
```

### 2. Fast Adaptation to New Project

```python
# Adapt to new project
response = httpx.post("http://localhost:8005/adapt", json={
    "project": "new_project",
    "days": 7,
    "target_accuracy": 0.80,
    "max_steps": 10
})
metrics = response.json()
print(f"Target reached: {metrics['target_met']}")
print(f"Steps: {metrics['metrics']['steps_to_target']}")
print(f"Accuracy: {metrics['metrics']['final_accuracy']}")
```

### 3. Check Adaptation Performance

```python
# Get adaptation metrics
response = httpx.get("http://localhost:8005/metrics/adaptation?days=7")
data = response.json()
target_check = data['target_performance']
print(f"Status: {target_check['status']}")
print(f"Avg steps to target: {target_check['avg_steps_to_target']}")
print(f"Avg accuracy: {target_check['avg_final_accuracy']}")
```

### 4. List Meta-Weights Versions

```python
# List versions
response = httpx.get("http://localhost:8005/meta-weights/versions")
versions = response.json()
print(f"Total versions: {versions['total']}")
print(f"Latest: {versions['latest']}")
```

## Performance Targets

### Primary Target
- **<10 steps to 80% accuracy** on new tasks
- Measured on query set after inner loop adaptation

### Meta-Training Metrics
- Mean task accuracy across all tasks
- Meta-loss convergence
- Training duration
- Failed plans integration rate

### Adaptation Metrics
- Steps to target (must be <10)
- Final accuracy (must be ≥80%)
- Success rate (percentage of adaptations meeting target)
- Per-project performance

## Database Schema

### maml_adaptation_metrics
```sql
CREATE TABLE maml_adaptation_metrics (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL,
    task_type VARCHAR(100),
    project VARCHAR(255),
    meta_version VARCHAR(50),
    steps_to_target INTEGER,
    target_reached BOOLEAN NOT NULL,
    target_accuracy FLOAT NOT NULL,
    final_accuracy FLOAT NOT NULL,
    final_loss FLOAT NOT NULL,
    adaptation_steps JSONB,
    losses JSONB,
    accuracies JSONB,
    num_support_samples INTEGER,
    num_query_samples INTEGER,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### maml_meta_training_metrics
```sql
CREATE TABLE maml_meta_training_metrics (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL,
    num_tasks INTEGER NOT NULL,
    num_outer_steps INTEGER NOT NULL,
    num_inner_steps INTEGER NOT NULL,
    final_meta_loss FLOAT NOT NULL,
    mean_task_accuracy FLOAT NOT NULL,
    meta_losses JSONB,
    task_accuracies JSONB,
    training_duration_seconds FLOAT,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Monitoring & Observability

### Key Metrics to Monitor

1. **Adaptation Performance**
   - Average steps to target
   - Success rate
   - Final accuracy distribution

2. **Meta-Training Health**
   - Meta-loss convergence
   - Task diversity
   - Training duration

3. **Replay Buffer**
   - Failed plans count
   - Effective weight distribution
   - Buffer utilization

4. **Storage**
   - Meta-weights versions count
   - Storage size
   - Version metadata

### Alerts

Set up alerts for:
- Average steps to target > 10
- Success rate < 80%
- Meta-training failures
- Scheduler execution failures

## Troubleshooting

### Issue: Target Not Met

**Symptoms:**
- Average steps to target > 10
- Success rate < 80%

**Solutions:**
1. Increase outer loop steps
2. Adjust learning rates
3. Increase task diversity
4. Add more failed plans to replay buffer
5. Check data quality

### Issue: Meta-Training Fails

**Symptoms:**
- Training job crashes
- Out of memory errors

**Solutions:**
1. Reduce batch sizes
2. Decrease number of tasks
3. Lower max_seq_length
4. Enable gradient checkpointing

### Issue: Poor Adaptation

**Symptoms:**
- High final loss
- Low accuracy

**Solutions:**
1. Check task data quality
2. Ensure sufficient support samples
3. Verify meta-weights loaded correctly
4. Try different task extraction strategy

## Best Practices

1. **Data Quality**
   - Ensure projects have sufficient feedback
   - Balance positive/negative samples
   - Clean and normalize data

2. **Task Diversity**
   - Use mixed extraction strategy
   - Include multiple projects
   - Cover different intents

3. **Failed Plans Integration**
   - Monitor failed plans buffer
   - Balance replay buffer ratios
   - Adjust weights if needed

4. **Meta-Weights Management**
   - Regular backups
   - Version comparison
   - Keep successful versions

5. **Monitoring**
   - Track adaptation metrics daily
   - Review meta-training logs
   - Set up performance alerts

## Future Enhancements

1. **First-Order MAML (FOMAML)**
   - Faster training with first-order gradients
   - Reduced memory footprint

2. **Reptile Algorithm**
   - Alternative meta-learning approach
   - Simpler implementation

3. **Task Clustering**
   - Group similar tasks
   - Reduce meta-training time

4. **Continual Meta-Learning**
   - Online meta-weight updates
   - Incremental task addition

5. **Multi-Task Meta-Learning**
   - Separate meta-weights per domain
   - Domain-specific adaptation

## References

- [MAML Paper](https://arxiv.org/abs/1703.03400)
- [First-Order MAML](https://arxiv.org/abs/1803.02999)
- [LoRA Paper](https://arxiv.org/abs/2106.09685)
- [Meta-Learning Survey](https://arxiv.org/abs/1810.03548)

## Support

For issues or questions:
1. Check logs: `docker logs maml-service`
2. Review metrics: `GET /metrics/adaptation`
3. Verify scheduler: `GET /scheduler/info`
4. Check component health: `GET /health`
