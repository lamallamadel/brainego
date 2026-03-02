# Pilot: Drift Detected Runbook

## Alert: DriftDetected / DriftMetricUnavailable

**Severity**: Warning (DriftDetected) / Info (DriftMetricUnavailable)  
**Component**: Drift Monitor  
**Pilot Critical**: Yes

---

## Overview

This alert fires when model drift is detected (`drift_score > 0.15`), indicating that the model's performance may be degrading due to changes in input data distribution or target concept. A separate informational alert fires if the `drift_score` metric is unavailable.

Model drift can indicate:
- Input data distribution has shifted (covariate shift)
- Target concept has changed (concept drift)
- Data quality degradation
- Feature engineering issues
- Model staleness

---

## Quick Diagnosis (3 minutes)

### Step 1: Check Drift Monitor Status

```bash
# Check drift-monitor service health
curl http://drift-monitor:8004/health

# Check if drift-monitor is running
docker compose ps drift-monitor
# or
kubectl get pods -l app=drift-monitor -n production

# Check drift monitor logs
docker compose logs --tail=50 drift-monitor
# or
kubectl logs -l app=drift-monitor --tail=50 -n production
```

### Step 2: Query Current Drift Score

```bash
# Check current drift score in Prometheus
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=drift_score'

# Check drift score over time
curl http://prometheus:9090/api/v1/query_range \
  --data-urlencode 'query=drift_score' \
  --data-urlencode 'start=<timestamp_24h_ago>' \
  --data-urlencode 'end=<timestamp_now>' \
  --data-urlencode 'step=300'

# Check Grafana drift dashboard
open http://localhost:3000/d/drift-monitor
```

### Step 3: Identify Affected Model

```bash
# Check which models are experiencing drift
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=drift_score > 0.15'

# Check drift monitor API for details
curl http://drift-monitor:8004/api/drift/current | jq

# Expected output:
# {
#   "model": "llama-3.3-8b",
#   "drift_score": 0.18,
#   "timestamp": "2025-01-30T10:45:23Z",
#   "features_affected": ["token_length", "prompt_complexity"]
# }
```

---

## Investigation Steps

### Phase 1: Drift Analysis

#### 1.1 Check Drift Details

```bash
# Get detailed drift report
curl http://drift-monitor:8004/api/drift/report | jq

# Check feature-level drift
curl http://drift-monitor:8004/api/drift/features | jq '.[] | select(.drift_score > 0.15)'

# Check prediction drift
curl http://drift-monitor:8004/api/drift/predictions | jq

# Check data quality metrics
curl http://drift-monitor:8004/api/drift/data-quality | jq
```

#### 1.2 Check Historical Drift Patterns

```bash
# Check drift events over time
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=increase(drift_detected_total[24h])'

# Check if drift is increasing or stable
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=deriv(drift_score[1h])'

# Check evaluation score changes
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=drift_baseline_accuracy - drift_current_accuracy'
```

#### 1.3 Check Recent Data Changes

```bash
# Check data collection service logs
docker compose logs --tail=200 data-collection | grep -i "error\|anomaly\|quality"

# Check for data source changes
curl http://data-collection:8002/api/sources/status | jq

# Check data volume changes
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=rate(data_ingestion_total[1h])'
```

---

### Phase 2: Root Cause Analysis

#### 2.1 Input Distribution Shift (Covariate Shift)

**Symptoms**: Feature drift score high, prediction drift low, model still performs well

```bash
# Check which features have highest drift
curl http://drift-monitor:8004/api/drift/features | jq 'sort_by(.drift_score) | reverse | .[0:5]'

# Check feature statistics
curl http://drift-monitor:8004/api/drift/feature-stats | jq

# Compare current vs baseline distributions
curl http://drift-monitor:8004/api/drift/distributions | jq
```

**Remediation**:

```bash
# Trigger model retraining with new data
curl -X POST http://learning-engine:8003/api/finetune/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b",
    "trigger_type": "drift_detected",
    "drift_score": 0.18
  }'

# Monitor retraining progress
curl http://learning-engine:8003/api/finetune/status | jq
```

#### 2.2 Concept Drift (Target Concept Changed)

**Symptoms**: Prediction drift high, evaluation score drop, model performance degraded

```bash
# Check evaluation score drop
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=drift_baseline_accuracy - drift_current_accuracy'

# Check prediction distribution change
curl http://drift-monitor:8004/api/drift/predictions | jq '.drift_score'

# Check for systematic errors
docker compose logs learning-engine | grep -i "evaluation\|accuracy\|f1"
```

**Remediation**:

```bash
# Emergency: Enable fallback model if available
curl -X POST http://api-server:8000/admin/model/fallback \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "reason": "concept_drift"}'

# Trigger emergency retraining with recent data
curl -X POST http://learning-engine:8003/api/finetune/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.3-8b",
    "trigger_type": "emergency",
    "priority": "high",
    "data_window": "last_7_days"
  }'

# Consider A/B testing with baseline model
curl -X POST http://api-server:8000/admin/ab-test/enable \
  -H "Content-Type: application/json" \
  -d '{
    "test_name": "drift_recovery",
    "model_a": "llama-3.3-8b-current",
    "model_b": "llama-3.3-8b-baseline",
    "traffic_split": 0.5
  }'
```

#### 2.3 Data Quality Degradation

**Symptoms**: High null rates, outliers, parsing errors in logs

```bash
# Check data quality metrics
curl http://drift-monitor:8004/api/drift/data-quality | jq

# Check for data quality alerts
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=data_quality_null_rate > 0.05 or data_quality_outlier_rate > 0.10'

# Check data collection errors
docker compose logs data-collection | grep -i "error\|failed\|invalid"
```

**Remediation**:

```bash
# Pause data collection from problematic sources
curl -X POST http://data-collection:8002/api/sources/pause \
  -H "Content-Type: application/json" \
  -d '{"source_id": "<problematic_source_id>"}'

# Enable data validation rules
curl -X POST http://data-collection:8002/api/validation/enable \
  -H "Content-Type: application/json" \
  -d '{
    "rules": ["null_check", "outlier_detection", "schema_validation"]
  }'

# Reprocess data with validation
curl -X POST http://data-collection:8002/api/reprocess \
  -H "Content-Type: application/json" \
  -d '{"start_time": "<timestamp>", "validate": true}'
```

#### 2.4 Feature Engineering Issues

**Symptoms**: Specific features show high drift, feature extraction errors in logs

```bash
# Check which features have issues
curl http://drift-monitor:8004/api/drift/features | jq '.[] | select(.drift_score > 0.25)'

# Check feature extraction logs
docker compose logs data-collection | grep -i "feature\|extraction\|transform"

# Check for missing features
curl http://drift-monitor:8004/api/drift/feature-stats | jq '.[] | select(.null_rate > 0.1)'
```

**Remediation**:

```bash
# Review and fix feature extraction code (code change required)
# Deploy updated feature extraction pipeline

# Re-extract features from raw data
curl -X POST http://data-collection:8002/api/features/recompute \
  -H "Content-Type: application/json" \
  -d '{"start_time": "<timestamp>", "features": ["token_length", "prompt_complexity"]}'
```

#### 2.5 Seasonal/Temporal Patterns

**Symptoms**: Drift score varies with time of day/week, cyclical pattern

```bash
# Check drift by time of day
curl http://drift-monitor:8004/api/drift/temporal-analysis | jq

# Check if drift correlates with traffic patterns
curl http://prometheus:9090/api/v1/query --data-urlencode 'query=rate(http_requests_total[1h])'
```

**Remediation**:

```bash
# Adjust drift detection thresholds for temporal patterns
curl -X PATCH http://drift-monitor:8004/api/config \
  -H "Content-Type: application/json" \
  -d '{
    "temporal_adjustment": true,
    "baseline_window": "same_hour_last_week"
  }'

# Train separate models for different time windows if needed
# (requires architecture change)
```

---

## Handling DriftMetricUnavailable Alert

If the `DriftMetricUnavailable` alert fires, the drift monitoring system is not reporting metrics.

### Diagnosis

```bash
# Check if drift-monitor is running
docker compose ps drift-monitor
kubectl get pods -l app=drift-monitor -n production

# Check drift-monitor logs
docker compose logs --tail=100 drift-monitor
kubectl logs -l app=drift-monitor --tail=100 -n production

# Check if drift-monitor can reach dependencies
docker compose exec drift-monitor ping postgres
docker compose exec drift-monitor ping api-server
```

### Remediation

```bash
# Restart drift-monitor service
docker compose restart drift-monitor
# or
kubectl rollout restart deployment/drift-monitor -n production

# Check configuration
curl http://drift-monitor:8004/api/config | jq

# Verify data collection is working
curl http://data-collection:8002/api/status | jq
```

---

## Remediation Summary

### Immediate Actions (10 minutes)

1. **Check Drift Severity**
   ```bash
   curl http://drift-monitor:8004/api/drift/current | jq '.drift_score'
   ```

2. **Check Model Performance**
   ```bash
   curl http://prometheus:9090/api/v1/query --data-urlencode 'query=drift_current_accuracy'
   ```

3. **Enable Fallback** (if performance degraded)
   ```bash
   curl -X POST http://api-server:8000/admin/model/fallback -d '{"enabled": true}'
   ```

4. **Trigger Retraining** (if drift confirmed)
   ```bash
   curl -X POST http://learning-engine:8003/api/finetune/trigger \
     -d '{"model": "llama-3.3-8b", "trigger_type": "drift_detected"}'
   ```

5. **Check Data Quality** (if data issues suspected)
   ```bash
   curl http://drift-monitor:8004/api/drift/data-quality | jq
   ```

### Long-term Actions

- Investigate root cause (distribution shift vs concept drift)
- Review and update feature engineering pipeline
- Adjust drift detection thresholds based on patterns
- Implement automatic retraining triggers
- Improve data validation and quality checks

---

## Prevention

### 1. Implement Automatic Retraining

```yaml
# Learning engine configuration
automatic_retraining:
  enabled: true
  triggers:
    - type: drift_detected
      threshold: 0.15
      cooldown: 24h
    - type: eval_score_drop
      threshold: 0.05
      cooldown: 12h
  schedule:
    - cron: "0 2 * * 0"  # Weekly on Sunday at 2 AM
```

### 2. Set Up Drift Monitoring Dashboards

```yaml
# Grafana dashboard for drift monitoring
- Panel: Drift Score Over Time
  query: drift_score
  
- Panel: Feature-Level Drift
  query: feature_drift_score
  
- Panel: Prediction Drift
  query: prediction_drift_score
  
- Panel: Evaluation Score
  query: drift_current_accuracy
```

### 3. Implement Gradual Model Updates

```python
# Example: Canary deployment for model updates
async def deploy_retrained_model(model_path):
    # Deploy to 10% traffic first
    await deploy_canary(model_path, traffic_split=0.1)
    
    # Monitor for 1 hour
    await asyncio.sleep(3600)
    
    # Check metrics
    if await validate_metrics(model_path):
        # Gradually increase traffic
        await deploy_canary(model_path, traffic_split=0.5)
        await asyncio.sleep(1800)
        await deploy_full(model_path)
    else:
        # Rollback
        await rollback_model()
```

### 4. Enhance Data Quality Checks

```python
# Example: Data validation pipeline
class DataValidator:
    def validate(self, data):
        checks = [
            self.check_null_rate(data) < 0.05,
            self.check_outlier_rate(data) < 0.10,
            self.check_schema_compliance(data),
            self.check_distribution_similarity(data)
        ]
        return all(checks)
```

### 5. Implement Drift Alerts

```yaml
# Multi-level drift alerting
- alert: DriftWarning
  expr: drift_score > 0.15
  for: 1m
  labels:
    severity: warning

- alert: DriftCritical
  expr: drift_score > 0.25
  for: 1m
  labels:
    severity: critical

- alert: EvalScoreDropped
  expr: (drift_baseline_accuracy - drift_current_accuracy) > 0.08
  for: 10m
  labels:
    severity: warning
```

### 6. Maintain Baseline Datasets

```bash
# Store baseline datasets for comparison
# Update baselines periodically (e.g., monthly)

# Store baseline
curl -X POST http://drift-monitor:8004/api/baseline/save \
  -H "Content-Type: application/json" \
  -d '{
    "name": "baseline_2025_01",
    "dataset_size": 10000,
    "period": "2025-01-01T00:00:00Z to 2025-01-31T23:59:59Z"
  }'

# List baselines
curl http://drift-monitor:8004/api/baseline/list | jq

# Update current baseline
curl -X POST http://drift-monitor:8004/api/baseline/update \
  -d '{"baseline_name": "baseline_2025_02"}'
```

---

## Related Alerts

- **HighDriftScore**: Severe drift (>0.25)
- **EvalScoreDropWarning**: Model accuracy declining
- **DriftEventSpike**: Multiple drift detections
- **FeatureDriftDetected**: Specific features showing drift
- **RetrainingMissingAfterDrift**: Automatic retraining not triggered

---

## Escalation

- **Immediate (<10 min)**: On-call ML Engineer
- **Within 30 min**: ML Team Lead (if severe drift)
- **Within 1 hour**: Data Science Team (if concept drift suspected)

---

## References

- [Drift Detection Algorithms](docs/refs/drift_detection.md)
- [Model Retraining Procedures](docs/refs/model_retraining.md)
- [Learning Engine Documentation](docs/refs/learning_engine.md)

---

**Version**: 1.0  
**Last Updated**: 2025-01-30  
**Owner**: ML Operations Team
