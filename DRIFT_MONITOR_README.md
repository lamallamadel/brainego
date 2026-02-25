# Drift Monitor Service

Automated model drift detection with KL Divergence, PSI (Population Stability Index), Slack alerting, and automatic fine-tuning trigger.

## Features

### 🎯 Core Capabilities
- **KL Divergence Calculation**: Measures distribution shift in embedding space using 7-day sliding windows
- **PSI Monitoring**: Tracks intent distribution stability across time periods
- **Accuracy Tracking**: Monitors model accuracy against configurable thresholds
- **YAML Configuration**: All thresholds and settings configurable via `configs/drift-monitor.yaml`
- **Slack Alerting**: Real-time notifications with severity levels (info, warning, critical)
- **Automatic Fine-Tuning**: Triggers learning engine when drift exceeds thresholds
- **Continuous Monitoring**: Background process with configurable check intervals

### 📊 Drift Detection Metrics

#### 1. KL Divergence (Embedding Distribution)
- Compares embedding distributions between baseline and current windows
- Uses histogram-based approach with 50 bins
- **Threshold**: 0.1 (configurable)
- Lower values = more similar distributions

#### 2. PSI (Intent Distribution)
- Measures shift in intent category distributions
- Standard PSI formula: `(actual% - expected%) * ln(actual% / expected%)`
- **Threshold**: 0.2 (configurable)
- PSI < 0.1: No significant change
- PSI 0.1-0.2: Moderate change
- PSI > 0.2: Significant drift

#### 3. Accuracy Monitoring
- Tracks positive feedback ratio (thumbs up / total)
- **Minimum Threshold**: 0.75 (75% accuracy)
- Triggers alert when accuracy drops below threshold

### 🚨 Alert Severity Levels

#### Critical (🔴)
- KL Divergence > 0.2 (2x threshold)
- PSI > 0.4 (2x threshold)
- Accuracy drop > 15%
- **Action**: Immediate Slack alert + automatic fine-tuning trigger

#### Warning (🟠)
- KL Divergence > 0.15 (1.5x threshold)
- PSI > 0.3 (1.5x threshold)
- Accuracy drop > 10%
- **Action**: Slack alert, manual review recommended

#### Info (🟢)
- KL Divergence > 0.1 (at threshold)
- PSI > 0.2 (at threshold)
- Accuracy drop > 5%
- **Action**: Informational Slack alert

## Configuration

### YAML Configuration (`configs/drift-monitor.yaml`)

```yaml
# Drift detection thresholds
thresholds:
  kl_threshold: 0.1         # KL Divergence threshold
  psi_threshold: 0.2        # PSI threshold
  accuracy_min: 0.75        # Minimum acceptable accuracy (75%)

# Monitoring windows
monitoring:
  sliding_window_days: 7    # 7-day sliding window for comparison
  check_interval_hours: 6   # Run drift checks every 6 hours
  min_samples: 100          # Minimum samples required for drift detection

# Embedding analysis
embeddings:
  model: "sentence-transformers/all-MiniLM-L6-v2"
  batch_size: 32
  dimension: 384

# Intent distribution tracking
intents:
  categories:
    - "code"
    - "reasoning"
    - "general"
    - "debug"
    - "documentation"
  min_samples_per_intent: 10

# Alerting configuration
alerts:
  enabled: true
  slack:
    enabled: true
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#drift-alerts"

# Fine-tuning trigger
fine_tuning:
  auto_trigger: true
  learning_engine_url: "http://learning-engine:8003"
  min_drift_score: 0.3      # Combined drift score threshold
  cooldown_hours: 168       # Wait 7 days between auto-triggered fine-tuning
```

### Environment Variables (`.env.drift.example`)

```bash
# Service
DRIFT_MONITOR_HOST=0.0.0.0
DRIFT_MONITOR_PORT=8004

# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password

# Slack (Optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Learning Engine
LEARNING_ENGINE_URL=http://learning-engine:8003
```

## API Endpoints

### Health Check
```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "is_monitoring": true,
  "config": {
    "kl_threshold": 0.1,
    "psi_threshold": 0.2,
    "accuracy_min": 0.75,
    "sliding_window_days": 7,
    "check_interval_hours": 6
  }
}
```

### Manual Drift Check
```bash
POST /drift/check
Content-Type: application/json

{
  "window_days": 7  # Optional: override sliding window
}
```

**Response:**
```json
{
  "status": "success",
  "drift_detected": true,
  "severity": "warning",
  "metrics": {
    "kl_divergence": 0.156,
    "psi": 0.234,
    "baseline_accuracy": 0.82,
    "current_accuracy": 0.74,
    "accuracy_delta": 0.08,
    "combined_drift_score": 0.45
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### Get Drift Metrics
```bash
GET /drift/metrics?days=30
```

**Response:**
```json
{
  "metrics": [
    {
      "id": 1,
      "kl_divergence": 0.156,
      "psi": 0.234,
      "baseline_accuracy": 0.82,
      "current_accuracy": 0.74,
      "drift_detected": true,
      "severity": "warning",
      "timestamp": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 1,
  "days": 30
}
```

### Get Drift Summary
```bash
GET /drift/summary
```

**Response:**
```json
{
  "summary": {
    "total_checks": 120,
    "drift_count": 15,
    "critical_count": 2,
    "warning_count": 8,
    "avg_kl": 0.085,
    "avg_psi": 0.142,
    "last_check": "2025-01-15T10:30:00Z"
  },
  "finetuning_triggers": 3,
  "last_finetuning_trigger": "2025-01-08T02:00:00Z",
  "is_monitoring": true
}
```

### Manually Trigger Fine-Tuning
```bash
POST /drift/trigger-finetuning
```

**Response:**
```json
{
  "status": "success",
  "message": "Fine-tuning triggered successfully",
  "drift_metrics": {
    "kl_divergence": 0.156,
    "psi": 0.234,
    "combined_drift_score": 0.45
  }
}
```

## Database Schema

### drift_metrics Table
```sql
CREATE TABLE drift_metrics (
    id SERIAL PRIMARY KEY,
    kl_divergence FLOAT NOT NULL,
    psi FLOAT NOT NULL,
    baseline_accuracy FLOAT NOT NULL,
    current_accuracy FLOAT NOT NULL,
    drift_detected BOOLEAN NOT NULL,
    severity VARCHAR(20),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### finetuning_triggers Table
```sql
CREATE TABLE finetuning_triggers (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255),
    drift_metrics JSONB,
    trigger_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## Usage

### Start Drift Monitor Service

#### Docker Compose
```bash
# Start all services including drift monitor
docker compose up -d drift-monitor

# View logs
docker compose logs -f drift-monitor

# Check health
curl http://localhost:8004/health
```

#### Standalone
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Run service
python drift_monitor.py
```

### Manual Drift Check
```bash
# Run immediate drift check
curl -X POST http://localhost:8004/drift/check

# With custom window
curl -X POST http://localhost:8004/drift/check \
  -H "Content-Type: application/json" \
  -d '{"window_days": 14}'
```

### Get Metrics
```bash
# Last 30 days
curl http://localhost:8004/drift/metrics?days=30

# Summary
curl http://localhost:8004/drift/summary
```

### Test Script
```bash
# Run comprehensive tests
python test_drift_monitor.py
```

## How It Works

### 1. Data Collection
- Fetches feedback data from PostgreSQL in two windows:
  - **Baseline**: Previous 7 days (offset by 7 days)
  - **Current**: Current 7 days (no offset)
- Requires minimum 100 samples per window

### 2. Embedding Analysis
- Computes sentence embeddings using `sentence-transformers/all-MiniLM-L6-v2`
- Concatenates query and response for each feedback item
- Generates 384-dimensional embeddings
- Calculates histogram-based KL Divergence between distributions

### 3. Intent Distribution Analysis
- Extracts intent categories from feedback data
- Calculates distribution percentages for each intent
- Computes PSI to measure distribution shift
- Formula: `Σ (current% - baseline%) * ln(current% / baseline%)`

### 4. Accuracy Calculation
- Computes accuracy as: `positive_feedback / total_feedback`
- Compares current accuracy to minimum threshold (0.75)
- Calculates accuracy delta between windows

### 5. Drift Detection
- **KL Drift**: `kl_divergence > 0.1`
- **PSI Drift**: `psi > 0.2`
- **Accuracy Drift**: `current_accuracy < 0.75`
- **Overall Drift**: Any of the above conditions met

### 6. Severity Assessment
- Calculates combined drift score from all metrics
- Determines severity level (critical, warning, info)
- Applies multipliers (1.0x, 1.5x, 2.0x) to thresholds

### 7. Alerting & Actions
- Sends Slack notification with metrics and severity
- Stores metrics in PostgreSQL for historical tracking
- Triggers automatic fine-tuning if:
  - Combined drift score ≥ 0.3
  - Cooldown period (7 days) has passed
  - Auto-trigger is enabled

### 8. Continuous Monitoring
- Runs checks every 6 hours (configurable)
- Background asyncio task
- Handles errors gracefully without stopping service

## Slack Alert Example

```
[WARNING] Model Drift Detected

Model drift detected with warning severity.
KL Divergence: 0.1560 (threshold: 0.1)
PSI: 0.2340 (threshold: 0.2)
Current Accuracy: 0.7400 (minimum: 0.75)
Combined Drift Score: 0.4500

Metrics:
• kl_divergence: 0.1560
• psi: 0.2340
• baseline_accuracy: 0.8200
• current_accuracy: 0.7400
• accuracy_delta: 0.0800
• combined_drift_score: 0.4500

Timestamp: 2025-01-15T10:30:00Z
Severity: WARNING

Drift Monitor Service
```

## Integration with Learning Engine

When drift is detected and the combined score exceeds the threshold:

1. **API Call**: POST request to `http://learning-engine:8003/train`
2. **Payload**: 
   ```json
   {
     "days": 7,
     "force": true
   }
   ```
3. **Cooldown**: 7-day cooldown to prevent over-training
4. **Tracking**: Records trigger in `finetuning_triggers` table
5. **Alert**: Sends Slack notification with job ID

## Best Practices

### Threshold Tuning
- Start with defaults (KL=0.1, PSI=0.2, Accuracy=0.75)
- Monitor false positive/negative rates
- Adjust thresholds based on your use case
- More strict thresholds = more sensitive detection

### Sample Requirements
- Ensure minimum 100 samples per window
- More samples = more reliable drift detection
- Consider increasing `min_samples` for high-traffic systems

### Alert Configuration
- Set up Slack webhook for team notifications
- Configure `mention_users` for critical alerts
- Adjust `check_interval_hours` based on traffic volume

### Fine-Tuning Strategy
- Set appropriate `cooldown_hours` (default: 168h = 7 days)
- Monitor fine-tuning success rates
- Adjust `min_drift_score` to balance sensitivity vs. frequency

### Performance Optimization
- Embedding computation is CPU-intensive
- Consider GPU acceleration for large datasets
- Adjust `embedding_batch_size` based on available memory

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker compose logs drift-monitor

# Common issues:
# - PostgreSQL not ready
# - Missing configuration file
# - Invalid YAML syntax
```

### Insufficient Samples
```
Drift check result: skipped (insufficient_samples)
```
- Wait for more feedback data to accumulate
- Reduce `min_samples` threshold
- Check if feedback is being collected properly

### High False Positive Rate
- Increase thresholds (KL, PSI)
- Increase `min_drift_score` for fine-tuning trigger
- Review intent distribution stability

### Slack Alerts Not Sending
- Verify `SLACK_WEBHOOK_URL` is set correctly
- Check Slack webhook is active
- Review service logs for error messages

### Fine-Tuning Not Triggering
- Check `auto_trigger: true` in config
- Verify drift score exceeds `min_drift_score`
- Confirm cooldown period has passed
- Check learning engine is running and healthy

## Monitoring & Observability

### Key Metrics to Track
- **Drift Detection Rate**: Percentage of checks that detect drift
- **False Positive Rate**: Drift alerts that don't correlate with actual issues
- **Fine-Tuning Triggers**: Frequency of automatic fine-tuning
- **KL Divergence Trend**: Gradual increase may indicate model decay
- **PSI Trend**: Sudden spikes indicate intent distribution shift
- **Accuracy Trend**: Declining accuracy requires investigation

### Logging
- All drift checks logged with metrics
- Slack alerts logged with response status
- Fine-tuning triggers logged with job IDs
- Errors logged with stack traces

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Drift Monitor Service                  │
│                     (Port 8004)                         │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼────────┐    ┌────────▼────────┐
│   PostgreSQL   │    │  Learning Engine│
│  - feedback    │    │   (Port 8003)   │
│  - drift_metrics    │   - Training    │
│  - finetuning_triggers  - Adapters   │
└────────────────┘    └─────────────────┘
        │
        │
┌───────▼────────┐
│  Slack Webhook │
│   - Alerts     │
└────────────────┘
```

## Related Services

- **Learning Engine** (`learning_engine_service.py`): Fine-tuning with LoRA and EWC
- **Feedback Service** (`feedback_service.py`): Collects user feedback
- **API Server** (`api_server.py`): Inference endpoint with feedback collection

## References

- [KL Divergence](https://en.wikipedia.org/wiki/Kullback%E2%80%93Leibler_divergence)
- [Population Stability Index (PSI)](https://www.listendata.com/2015/05/population-stability-index.html)
- [Model Drift Detection](https://docs.seldon.io/projects/alibi-detect/en/stable/cd/background.html)
- [Sentence Transformers](https://www.sbert.net/)

## License

Part of the AI Platform - see main repository for license information.
