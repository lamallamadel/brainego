# Grafana Dashboards for Drift Monitoring

Comprehensive monitoring dashboards for model drift detection, LoRA adapter tracking, and historical performance comparison.

## 🎯 Overview

This implementation provides 5 Grafana dashboards integrated with Prometheus and PostgreSQL for complete visibility into:
- **KL Divergence Evolution**: Track embedding distribution drift over time
- **PSI Trends**: Monitor intent distribution stability
- **Accuracy Tracking**: Baseline vs current accuracy comparison
- **LoRA Version Management**: Track adapter versions with historical metrics
- **Unified Overview**: Combined view of all drift metrics

## 📊 Available Dashboards

### 1. Drift Monitoring - Overview
**UID**: `drift-overview`  
**Description**: Unified dashboard showing all key drift metrics in one view

**Key Panels**:
- Current KL Divergence, PSI, Accuracy, and Combined Score (Gauges)
- All drift metrics timeline (combined graph)
- Total checks, detections, and fine-tuning triggers
- Recent drift checks table with severity highlighting

**Use Case**: First-stop dashboard for quick drift status assessment

---

### 2. Drift Monitoring - KL Divergence Evolution
**UID**: `drift-kl-divergence`  
**Description**: Detailed KL Divergence tracking with threshold visualization

**Key Panels**:
- Real-time KL Divergence from Prometheus
- Historical KL Divergence from PostgreSQL
- Current KL Divergence gauge
- 7-day average KL Divergence
- Drift status indicator

**Thresholds**:
- Green: < 0.1 (No drift)
- Yellow: 0.1 - 0.15 (Baseline)
- Orange: 0.15 - 0.2 (Moderate drift)
- Red: > 0.2 (Critical drift)

**Annotations**: Automatic markers when drift is detected

---

### 3. Drift Monitoring - PSI Trends
**UID**: `drift-psi-trends`  
**Description**: Population Stability Index monitoring for intent distributions

**Key Panels**:
- Real-time PSI from Prometheus
- Historical PSI from PostgreSQL
- Current PSI gauge
- 7-day average PSI
- PSI drift event counter
- Recent PSI measurements table

**Thresholds**:
- Green: < 0.1 (No change)
- Yellow: 0.1 - 0.2 (Moderate change)
- Orange: 0.2 - 0.3 (Significant change)
- Red: > 0.3 (Critical drift)

**Annotations**: Markers when PSI exceeds threshold

---

### 4. Drift Monitoring - Accuracy Over Time
**UID**: `drift-accuracy-tracking`  
**Description**: Model accuracy tracking with baseline comparison

**Key Panels**:
- Baseline vs Current accuracy timeline
- Historical accuracy comparison from database
- Current accuracy gauge
- Baseline accuracy gauge
- Accuracy delta indicator
- Low accuracy event counter
- Daily average accuracy bar chart (30 days)

**Thresholds**:
- Green: > 80% (Excellent)
- Yellow: 75-80% (Acceptable)
- Orange: 70-75% (Warning)
- Red: < 70% (Critical)

**Annotations**: Markers when accuracy drops below 75%

---

### 5. LoRA Version Tracking & Historical Comparison
**UID**: `lora-version-tracking`  
**Description**: Comprehensive LoRA adapter versioning and performance tracking

**Key Panels**:
- **Version Table**: All LoRA adapters with training metrics
  - Version, base model, rank, alpha
  - Training/validation loss
  - Active status
  - Creation and deployment dates
- **Training Loss Timeline**: Training and validation loss evolution
- **Training Time**: Time taken per version
- **Version Statistics**:
  - Total adapters
  - Active adapters
  - Active adapter training loss
  - Current active version
- **Performance Comparison**: Multi-version metric comparison
- **Distribution Charts**:
  - Adapters by base model (pie chart)
  - Adapters by LoRA rank (donut chart)

**Annotations**:
- Green: New adapter created
- Blue: Adapter deployed
- Purple: Fine-tuning triggered

---

## 🚀 Setup & Configuration

### 1. Start Services

```bash
# Start Prometheus, Grafana, and Drift Monitor
docker compose up -d prometheus grafana drift-monitor

# Verify services are running
docker compose ps
```

### 2. Access Grafana

**URL**: http://localhost:3000  
**Default Credentials**:
- Username: `admin`
- Password: `admin`

**Change password on first login**

### 3. Pre-configured Datasources

The following datasources are automatically provisioned:

#### Prometheus
- **Name**: Prometheus
- **URL**: http://prometheus:9090
- **Type**: Time-series metrics
- **Refresh**: 15s

#### PostgreSQL
- **Name**: PostgreSQL
- **URL**: postgres:5432
- **Database**: ai_platform
- **Type**: Relational data
- **User**: ai_user

### 4. Dashboard Auto-Loading

All dashboards are automatically loaded from:
```
configs/grafana/dashboards/
├── drift-overview.json
├── drift-kl-divergence.json
├── drift-psi-trends.json
├── drift-accuracy-tracking.json
└── lora-version-tracking.json
```

## 📈 Metrics Exposed

### Prometheus Metrics (from Drift Monitor)

| Metric Name | Type | Description | Labels |
|-------------|------|-------------|--------|
| `drift_checks_total` | Counter | Total drift checks performed | `status` |
| `drift_detected_total` | Counter | Total drift detections | `severity` |
| `drift_kl_divergence` | Gauge | Current KL Divergence value | - |
| `drift_psi` | Gauge | Current PSI value | - |
| `drift_baseline_accuracy` | Gauge | Baseline accuracy | - |
| `drift_current_accuracy` | Gauge | Current accuracy | - |
| `drift_combined_score` | Gauge | Combined drift score | - |
| `finetuning_triggers_total` | Counter | Fine-tuning triggers | `trigger_type` |
| `drift_check_duration_seconds` | Histogram | Drift check duration | - |

### PostgreSQL Tables

#### drift_metrics
```sql
- id (SERIAL)
- kl_divergence (FLOAT)
- psi (FLOAT)
- baseline_accuracy (FLOAT)
- current_accuracy (FLOAT)
- drift_detected (BOOLEAN)
- severity (VARCHAR)
- timestamp (TIMESTAMP)
```

#### lora_adapters
```sql
- id (SERIAL)
- version (VARCHAR)
- training_job_id (VARCHAR)
- base_model (VARCHAR)
- rank, alpha, dropout (INT/FLOAT)
- training_loss, validation_loss (FLOAT)
- training_time_seconds (INT)
- is_active (BOOLEAN)
- created_at, deployed_at (TIMESTAMP)
```

#### lora_performance
```sql
- id (SERIAL)
- adapter_version (VARCHAR)
- metric_name (VARCHAR)
- metric_value (FLOAT)
- timestamp (TIMESTAMP)
```

## 🎨 Dashboard Features

### Time Range Controls
- Default: Last 7 days (drift metrics)
- Default: Last 30 days (LoRA tracking)
- Customizable via time picker
- Auto-refresh: 30s - 1m

### Annotations
- **Drift Detected**: Red markers on drift events
- **New LoRA Adapter**: Green markers on creation
- **Adapter Deployed**: Blue markers on deployment
- **Fine-tuning Triggered**: Purple markers

### Alert Thresholds
All thresholds are visually coded:
- **Green**: Healthy state
- **Yellow**: Warning threshold
- **Orange**: Moderate concern
- **Red**: Critical state requiring action

### Interactive Features
- Click on any panel to zoom/drill-down
- Hover for detailed tooltips
- Legend shows last/mean/max values
- Table sorting and filtering

## 🔧 Customization

### Modify Thresholds

Edit dashboard JSON files in `configs/grafana/dashboards/` and update threshold values:

```json
"thresholds": {
  "mode": "absolute",
  "steps": [
    {"color": "green", "value": null},
    {"color": "yellow", "value": 0.1},
    {"color": "red", "value": 0.2}
  ]
}
```

### Add Custom Panels

1. Open Grafana UI
2. Navigate to dashboard
3. Click "Add Panel"
4. Configure query (Prometheus or PostgreSQL)
5. Save dashboard
6. Export JSON to `configs/grafana/dashboards/`

### Custom Queries

#### Prometheus (PromQL)
```promql
# Drift rate over 5 minutes
rate(drift_detected_total[5m])

# Average KL Divergence
avg_over_time(drift_kl_divergence[1h])

# Fine-tuning trigger rate
rate(finetuning_triggers_total[1h])
```

#### PostgreSQL (SQL)
```sql
-- Drift frequency by day
SELECT 
  DATE(timestamp) as day,
  COUNT(*) FILTER (WHERE drift_detected = true) as drift_count
FROM drift_metrics
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY DATE(timestamp)
ORDER BY day;

-- Adapter performance comparison
SELECT 
  version,
  AVG(metric_value) as avg_performance
FROM lora_performance
WHERE metric_name = 'accuracy'
GROUP BY version
ORDER BY avg_performance DESC;
```

## 📱 Alerting (Optional)

### Configure Grafana Alerts

1. Navigate to **Alerting** → **Alert rules**
2. Create new alert rule
3. Configure query and condition:
   ```
   Query: drift_kl_divergence
   Condition: > 0.2 for 5m
   ```
4. Set notification channel (email, Slack, PagerDuty)

### Alert Examples

**Critical Drift Alert**:
```
Alert: Critical Drift Detected
Condition: drift_combined_score > 0.7 for 10m
Severity: Critical
Notification: Slack #drift-alerts
```

**Low Accuracy Alert**:
```
Alert: Model Accuracy Below Threshold
Condition: drift_current_accuracy < 0.7 for 15m
Severity: Warning
Notification: Email to ML team
```

## 🔍 Troubleshooting

### Dashboards Not Loading

```bash
# Check Grafana logs
docker compose logs grafana

# Verify provisioning directory
docker compose exec grafana ls -la /etc/grafana/provisioning/dashboards

# Restart Grafana
docker compose restart grafana
```

### No Data in Panels

```bash
# Verify Prometheus is scraping
curl http://localhost:9090/api/v1/targets

# Check drift monitor metrics endpoint
curl http://localhost:8004/metrics

# Verify PostgreSQL connection
docker compose exec grafana grafana-cli admin data-migration list-sources
```

### Datasource Connection Issues

```bash
# Test Prometheus connectivity
docker compose exec grafana wget -qO- http://prometheus:9090/api/v1/query?query=up

# Test PostgreSQL connectivity
docker compose exec grafana pg_isready -h postgres -p 5432 -U ai_user
```

### Metrics Not Updating

```bash
# Check drift monitor is running checks
docker compose logs drift-monitor | grep "Running Drift Detection"

# Verify Prometheus scrape interval
curl http://localhost:9090/api/v1/status/config | jq .data.yaml | grep scrape_interval

# Force a manual drift check
curl -X POST http://localhost:8004/drift/check
```

## 📊 Best Practices

### Dashboard Usage
1. **Start with Overview**: Check drift-overview dashboard daily
2. **Drill Down on Anomalies**: Use specific dashboards for investigation
3. **Monitor Trends**: Look for gradual increases over weeks
4. **Compare Versions**: Use LoRA tracking to correlate drift with deployments

### Performance Optimization
1. **Limit Time Ranges**: Use 7-30 days for most queries
2. **Increase Refresh Intervals**: Use 1m for production (30s for dev)
3. **Archive Old Data**: PostgreSQL retention policies for drift_metrics
4. **Index Optimization**: Ensure indexes on timestamp columns

### Alert Strategy
1. **Layered Alerts**:
   - Info: Drift detected (log only)
   - Warning: Sustained drift (Slack)
   - Critical: Multiple metrics drifting (PagerDuty)
2. **Avoid Alert Fatigue**: Set reasonable thresholds
3. **Actionable Alerts**: Include runbook links

## 🔗 Integration with Other Services

### Jaeger (Tracing)
Link Grafana with Jaeger for end-to-end request tracing:
- Drift check → Fine-tuning trigger → Model deployment

### Slack Alerts
Drift Monitor already sends Slack alerts. Complement with Grafana alerts for dashboard-specific thresholds.

### MinIO (Storage)
LoRA adapters stored in MinIO are tracked via PostgreSQL metadata, visible in LoRA Version Tracking dashboard.

## 📚 References

- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [PostgreSQL Datasource](https://grafana.com/docs/grafana/latest/datasources/postgres/)
- [Dashboard Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)

## 🎓 Learning Resources

### Grafana
- Official tutorials: https://grafana.com/tutorials/
- Community dashboards: https://grafana.com/grafana/dashboards/

### PromQL
- Basics: https://prometheus.io/docs/prometheus/latest/querying/basics/
- Functions: https://prometheus.io/docs/prometheus/latest/querying/functions/

### PostgreSQL with Grafana
- Time-series queries: https://grafana.com/blog/2020/03/23/how-to-visualize-time-series-data-in-grafana/

## 📝 Dashboard Maintenance

### Regular Tasks
- **Weekly**: Review alert accuracy, adjust thresholds
- **Monthly**: Archive old drift_metrics data
- **Quarterly**: Optimize dashboard performance
- **Yearly**: Review and update KPIs

### Version Control
All dashboard JSON files are version controlled in:
```
configs/grafana/dashboards/
```

Export updated dashboards:
1. Grafana UI → Dashboard Settings → JSON Model
2. Copy JSON
3. Save to `configs/grafana/dashboards/<name>.json`
4. Commit to git

## 🎯 Next Steps

1. **Customize Thresholds**: Adjust based on your model characteristics
2. **Add Custom Metrics**: Track domain-specific drift indicators
3. **Set Up Alerts**: Configure Grafana alerting for critical metrics
4. **Create Playlists**: Auto-rotate dashboards on displays
5. **Export Reports**: Schedule PDF reports via Grafana Reporting

## 📞 Support

For issues or questions:
- Check `DRIFT_MONITOR_README.md` for drift detection details
- Review Grafana logs: `docker compose logs grafana`
- Consult Prometheus metrics: http://localhost:9090

---

**Last Updated**: 2025-01-25  
**Version**: 1.0.0  
**Maintainer**: AI Platform Team
