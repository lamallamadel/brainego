# Drift Monitor Quick Start Guide

Get started with model drift detection in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- PostgreSQL running with feedback data
- (Optional) Slack webhook URL for alerts

## Quick Start

### 1. Configure Environment

```bash
# Copy example environment file
cp .env.drift.example .env.drift

# Edit with your settings
nano .env.drift
```

**Minimum configuration:**
```bash
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password
```

**With Slack alerts:**
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 2. Start Drift Monitor

```bash
# Start the service
docker compose up -d drift-monitor

# Check logs
docker compose logs -f drift-monitor
```

Expected output:
```
Starting Drift Monitor Service...
Configuration: KL threshold=0.1, PSI threshold=0.2
✓ Drift Monitor initialized
✓ Drift monitoring started
Drift Monitor Service ready!
```

### 3. Verify Service is Running

```bash
# Health check
curl http://localhost:8004/health
```

**Expected response:**
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

### 4. Run Your First Drift Check

```bash
# Trigger manual drift check
curl -X POST http://localhost:8004/drift/check | jq
```

**If sufficient data:**
```json
{
  "status": "success",
  "drift_detected": false,
  "severity": null,
  "metrics": {
    "kl_divergence": 0.045,
    "psi": 0.089,
    "baseline_accuracy": 0.82,
    "current_accuracy": 0.80,
    "accuracy_delta": 0.02,
    "combined_drift_score": 0.12
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

**If insufficient data:**
```json
{
  "status": "skipped",
  "reason": "insufficient_samples",
  "baseline_count": 45,
  "current_count": 52
}
```

### 5. View Drift Metrics

```bash
# Get historical metrics
curl http://localhost:8004/drift/metrics?days=7 | jq

# Get summary
curl http://localhost:8004/drift/summary | jq
```

## Understanding Results

### No Drift (✅ Good)
```json
{
  "drift_detected": false,
  "metrics": {
    "kl_divergence": 0.045,  // < 0.1 threshold
    "psi": 0.089,            // < 0.2 threshold
    "current_accuracy": 0.80 // > 0.75 minimum
  }
}
```

### Drift Detected (⚠️ Warning)
```json
{
  "drift_detected": true,
  "severity": "warning",
  "metrics": {
    "kl_divergence": 0.156,  // > 0.1 threshold
    "psi": 0.234,            // > 0.2 threshold
    "current_accuracy": 0.74 // < 0.75 minimum
  }
}
```

### Critical Drift (🚨 Urgent)
```json
{
  "drift_detected": true,
  "severity": "critical",
  "metrics": {
    "kl_divergence": 0.245,  // > 0.2 (2x threshold)
    "psi": 0.456,            // > 0.4 (2x threshold)
    "current_accuracy": 0.65 // 17% drop
  }
}
```

## What Happens Next?

### Automatic Monitoring
- Runs every **6 hours** by default
- Checks last 7 days vs previous 7 days
- Stores metrics in PostgreSQL

### When Drift is Detected
1. **Metrics stored** in `drift_metrics` table
2. **Slack alert sent** (if configured)
3. **Fine-tuning triggered** if drift score ≥ 0.3
4. **Cooldown period** of 7 days between auto-triggers

### Manual Fine-Tuning Trigger
```bash
# Force fine-tuning regardless of drift
curl -X POST http://localhost:8004/drift/trigger-finetuning | jq
```

## Configuration Tips

### Adjust Thresholds

Edit `configs/drift-monitor.yaml`:

```yaml
# More sensitive (detect smaller changes)
thresholds:
  kl_threshold: 0.05    # Default: 0.1
  psi_threshold: 0.15   # Default: 0.2
  accuracy_min: 0.80    # Default: 0.75

# Less sensitive (only major changes)
thresholds:
  kl_threshold: 0.15
  psi_threshold: 0.25
  accuracy_min: 0.70
```

### Change Check Frequency

```yaml
monitoring:
  check_interval_hours: 12  # Default: 6 (every 6 hours)
```

### Adjust Fine-Tuning Trigger

```yaml
fine_tuning:
  auto_trigger: true
  min_drift_score: 0.5      # Default: 0.3 (higher = less frequent)
  cooldown_hours: 336       # Default: 168 (7 days)
```

## Common Scenarios

### Scenario 1: High Traffic System
```yaml
monitoring:
  sliding_window_days: 3     # Shorter window
  check_interval_hours: 2    # More frequent checks
  min_samples: 500           # Higher sample requirement
```

### Scenario 2: Low Traffic System
```yaml
monitoring:
  sliding_window_days: 14    # Longer window
  check_interval_hours: 24   # Daily checks
  min_samples: 50            # Lower sample requirement
```

### Scenario 3: Production Critical
```yaml
thresholds:
  kl_threshold: 0.08         # More sensitive
  psi_threshold: 0.15
  accuracy_min: 0.80

fine_tuning:
  min_drift_score: 0.25      # Trigger sooner
  cooldown_hours: 84         # 3.5 days
```

## Testing Your Setup

### Generate Test Feedback Data

```python
import psycopg2
import random
from datetime import datetime, timedelta

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="ai_platform",
    user="ai_user",
    password="ai_password"
)

cursor = conn.cursor()

# Generate 200 feedback samples over 14 days
intents = ["code", "reasoning", "general", "debug"]
for i in range(200):
    days_ago = random.randint(0, 13)
    timestamp = datetime.now() - timedelta(days=days_ago)
    
    cursor.execute(
        """
        INSERT INTO feedback (
            feedback_id, query, response, model, rating, 
            intent, timestamp
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            f"test_{i}",
            f"Test query {i}",
            f"Test response {i}",
            "test-model",
            random.choice([1, -1]),
            random.choice(intents),
            timestamp
        )
    )

conn.commit()
cursor.close()
conn.close()
print("✓ Generated 200 test feedback samples")
```

### Run Test Script

```bash
python test_drift_monitor.py
```

## Monitoring Dashboard

View metrics in your database:

```sql
-- Recent drift checks
SELECT * FROM drift_metrics 
ORDER BY timestamp DESC 
LIMIT 10;

-- Drift summary
SELECT 
    COUNT(*) as total_checks,
    COUNT(*) FILTER (WHERE drift_detected) as drift_count,
    AVG(kl_divergence) as avg_kl,
    AVG(psi) as avg_psi
FROM drift_metrics
WHERE timestamp >= NOW() - INTERVAL '30 days';

-- Fine-tuning triggers
SELECT * FROM finetuning_triggers
ORDER BY trigger_timestamp DESC;
```

## Troubleshooting

### Service won't start
```bash
# Check dependencies
docker compose ps

# View detailed logs
docker compose logs drift-monitor

# Restart service
docker compose restart drift-monitor
```

### No drift checks running
```bash
# Verify monitoring is active
curl http://localhost:8004/health | jq '.is_monitoring'

# Check logs for errors
docker compose logs -f drift-monitor
```

### Insufficient samples error
```bash
# Check feedback data
psql -h localhost -U ai_user -d ai_platform \
  -c "SELECT COUNT(*) FROM feedback WHERE timestamp >= NOW() - INTERVAL '7 days';"

# Reduce min_samples in config
# OR wait for more feedback data
```

### Slack alerts not working
```bash
# Test webhook directly
curl -X POST YOUR_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"text": "Test alert"}'

# Verify environment variable
docker compose exec drift-monitor env | grep SLACK_WEBHOOK_URL
```

## Next Steps

1. **Set up Slack alerts** for your team
2. **Adjust thresholds** based on initial observations
3. **Monitor false positive rate** and tune accordingly
4. **Review drift patterns** weekly
5. **Correlate drift with model performance** in production

## Resources

- **Full Documentation**: `DRIFT_MONITOR_README.md`
- **API Reference**: See README for endpoint details
- **Configuration**: `configs/drift-monitor.yaml`
- **Database Schema**: `init-scripts/postgres/init.sql`

## Support

If you encounter issues:
1. Check logs: `docker compose logs drift-monitor`
2. Verify configuration: `curl http://localhost:8004/health`
3. Review feedback data availability
4. Adjust thresholds if needed

---

**Ready to deploy?** Continue to production deployment guide in the main README.
