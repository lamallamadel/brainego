# Grafana Dashboards - Quick Start Guide

Get your drift monitoring dashboards up and running in 5 minutes.

## 🚀 Quick Setup

### Step 1: Start Services

```bash
# Start Prometheus, Grafana, and Drift Monitor
docker compose up -d prometheus grafana drift-monitor postgres

# Wait for services to be healthy (30-60 seconds)
docker compose ps
```

### Step 2: Access Grafana

1. Open browser: http://localhost:3000
2. Login with default credentials:
   - **Username**: `admin`
   - **Password**: `admin`
3. Change password when prompted (or skip)

### Step 3: View Dashboards

Navigate to **Dashboards** → **Browse** or use direct links:

- **Overview**: http://localhost:3000/d/drift-overview
- **KL Divergence**: http://localhost:3000/d/drift-kl-divergence
- **PSI Trends**: http://localhost:3000/d/drift-psi-trends
- **Accuracy**: http://localhost:3000/d/drift-accuracy-tracking
- **LoRA Versions**: http://localhost:3000/d/lora-version-tracking

### Step 4: Generate Sample Data (Optional)

```bash
# Trigger manual drift check
curl -X POST http://localhost:8004/drift/check

# Check metrics are being collected
curl http://localhost:8004/metrics

# View in Prometheus
open http://localhost:9090
```

## 📊 Dashboard Overview

### 1. Drift Monitoring - Overview
**Best for**: Daily health checks

**Shows**:
- ✅ Current drift status (4 gauges)
- 📈 All metrics combined timeline
- 🔢 Total checks and detections
- 📋 Recent drift check history

**Time Range**: Last 6 hours  
**Refresh**: 30 seconds

---

### 2. KL Divergence Evolution
**Best for**: Embedding distribution drift analysis

**Shows**:
- 📊 Real-time KL Divergence
- 📉 Historical trends
- 🎯 Current value vs threshold
- 📅 7-day average

**Time Range**: Last 7 days  
**Refresh**: 30 seconds

**Thresholds**:
- 🟢 < 0.1: No drift
- 🟡 0.1-0.15: Warning
- 🟠 0.15-0.2: Moderate
- 🔴 > 0.2: Critical

---

### 3. PSI Trends
**Best for**: Intent distribution stability monitoring

**Shows**:
- 📊 Real-time PSI
- 📉 Historical PSI trends
- 🎯 Current PSI gauge
- 📊 PSI event counter
- 📋 Recent measurements

**Time Range**: Last 7 days  
**Refresh**: 30 seconds

**Thresholds**:
- 🟢 < 0.1: Stable
- 🟡 0.1-0.2: Moderate shift
- 🟠 0.2-0.3: Significant shift
- 🔴 > 0.3: Critical drift

---

### 4. Accuracy Over Time
**Best for**: Model performance tracking

**Shows**:
- 📊 Baseline vs Current accuracy
- 📈 Daily accuracy trends
- 🎯 Accuracy delta
- 📉 Low accuracy events
- 📊 30-day bar chart

**Time Range**: Last 7 days  
**Refresh**: 30 seconds

**Thresholds**:
- 🟢 > 80%: Excellent
- 🟡 75-80%: Good
- 🟠 70-75%: Warning
- 🔴 < 70%: Critical

---

### 5. LoRA Version Tracking
**Best for**: Adapter management and comparison

**Shows**:
- 📋 All adapter versions
- 📊 Training/validation loss
- ⏱️ Training time per version
- 📈 Performance comparison
- 📊 Distribution by model/rank

**Time Range**: Last 30 days  
**Refresh**: 1 minute

---

## 🎯 Common Tasks

### Check Current Drift Status
1. Go to **Drift Monitoring - Overview**
2. Look at the 4 gauges at the top
3. Green = healthy, Yellow/Orange = warning, Red = action needed

### Investigate Drift Detection
1. Note which metric triggered (KL/PSI/Accuracy)
2. Open the specific dashboard (e.g., KL Divergence)
3. Look at timeline to see when drift started
4. Check annotations for related events

### Compare LoRA Versions
1. Open **LoRA Version Tracking**
2. View the versions table
3. Check training loss trends
4. Compare performance metrics graph
5. Identify active version

### Track Fine-tuning Impact
1. Open **LoRA Version Tracking**
2. Look for "Fine-tuning Triggered" annotations (purple)
3. Check training loss for new version
4. Switch to **Accuracy** dashboard
5. Observe accuracy improvement post-deployment

## 🔧 Configuration

### Change Refresh Rate
1. Open any dashboard
2. Click refresh dropdown (top-right)
3. Select: 5s, 10s, 30s, 1m, 5m, 15m, 30m, 1h

### Adjust Time Range
1. Click time range (top-right)
2. Select preset: Last 5m, 15m, 1h, 6h, 12h, 24h, 7d, 30d
3. Or set custom: Absolute/Relative time

### Modify Thresholds
1. Dashboard Settings (⚙️ icon)
2. JSON Model tab
3. Edit `thresholds` values
4. Save dashboard

## 📈 Metrics Endpoints

### Prometheus Metrics
```bash
# Drift Monitor metrics
curl http://localhost:8004/metrics

# Prometheus UI
open http://localhost:9090
```

### PostgreSQL Data
```bash
# Connect to database
docker compose exec postgres psql -U ai_user -d ai_platform

# Query drift metrics
SELECT * FROM drift_metrics ORDER BY timestamp DESC LIMIT 10;

# Query LoRA adapters
SELECT version, training_loss, is_active FROM lora_adapters ORDER BY created_at DESC;
```

## 🚨 Alerts

### View Active Alerts
1. Navigate to **Alerting** → **Alert rules**
2. Check firing status
3. View alert details

### Create New Alert
1. Go to dashboard panel
2. Click panel title → **Edit**
3. **Alert** tab → **Create alert**
4. Configure:
   - Query/Condition
   - Evaluation interval
   - Notification channel

## 🔍 Troubleshooting

### No Data in Dashboards

**Check 1: Services Running**
```bash
docker compose ps
# All services should show "Up" and "healthy"
```

**Check 2: Drift Monitor Running Checks**
```bash
docker compose logs drift-monitor | tail -20
# Should see "Running Drift Detection Check"
```

**Check 3: Metrics Endpoint**
```bash
curl http://localhost:8004/metrics | grep drift_kl
# Should return metric values
```

**Check 4: Prometheus Scraping**
```bash
# Open Prometheus UI
open http://localhost:9090/targets
# drift-monitor should show "UP" status
```

---

### Datasource Connection Failed

**PostgreSQL**:
```bash
# Test connection
docker compose exec grafana psql -h postgres -U ai_user -d ai_platform -c "SELECT 1"
```

**Prometheus**:
```bash
# Test connection
docker compose exec grafana wget -qO- http://prometheus:9090/api/v1/query?query=up
```

---

### Dashboards Not Auto-Loading

**Check provisioning**:
```bash
# List dashboards
docker compose exec grafana ls -la /var/lib/grafana/dashboards

# Check provisioning config
docker compose exec grafana cat /etc/grafana/provisioning/dashboards/dashboards.yml
```

**Reload**:
```bash
docker compose restart grafana
```

---

## 📊 Sample Queries

### Prometheus (PromQL)

**Drift detection rate**:
```promql
rate(drift_detected_total[5m])
```

**Average KL Divergence (1 hour)**:
```promql
avg_over_time(drift_kl_divergence[1h])
```

**Fine-tuning triggers per hour**:
```promql
rate(finetuning_triggers_total[1h])
```

### PostgreSQL (SQL)

**Recent drift events**:
```sql
SELECT timestamp, kl_divergence, psi, severity 
FROM drift_metrics 
WHERE drift_detected = true 
ORDER BY timestamp DESC 
LIMIT 10;
```

**Adapter performance**:
```sql
SELECT version, training_loss, validation_loss, is_active
FROM lora_adapters
ORDER BY created_at DESC;
```

## 🎨 Dashboard Links

Create quick access bookmarks:

```
Overview:      http://localhost:3000/d/drift-overview
KL Divergence: http://localhost:3000/d/drift-kl-divergence
PSI Trends:    http://localhost:3000/d/drift-psi-trends
Accuracy:      http://localhost:3000/d/drift-accuracy-tracking
LoRA Tracking: http://localhost:3000/d/lora-version-tracking
```

## 📱 Mobile Access

Grafana dashboards work on mobile:
1. Use http://[your-server-ip]:3000 from mobile browser
2. Dashboards are responsive
3. Touch gestures supported (pinch-to-zoom)

## 🎯 Next Steps

1. ✅ Set up dashboards (you're done!)
2. 📊 Monitor for a few days to establish baseline
3. 🔔 Configure alerts for critical metrics
4. 📈 Customize thresholds based on your data
5. 📚 Read full documentation: `GRAFANA_DASHBOARDS.md`

## 📞 Need Help?

- **Drift Monitor Issues**: See `DRIFT_MONITOR_README.md`
- **Grafana Docs**: https://grafana.com/docs/
- **Prometheus Docs**: https://prometheus.io/docs/

---

**Setup Time**: 5 minutes  
**Skill Level**: Beginner  
**Last Updated**: 2025-01-25
