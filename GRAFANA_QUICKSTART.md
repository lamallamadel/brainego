# Grafana Dashboards Quick Start Guide

## Quick Access

### Dashboard URLs
- **Platform Overview**: `http://localhost:3000/d/platform-overview`
- **Learning Engine**: `http://localhost:3000/d/learning-engine`
- **MCP Activity**: `http://localhost:3000/d/mcp-activity`

Default Grafana credentials:
- Username: `admin`
- Password: `admin` (change on first login)

## Dashboard Summary

### 1. Platform Overview
**Purpose**: Real-time platform health monitoring  
**Key Metrics**: Latency P99, Error Rate, GPU Utilization, Token Usage, Memory Hit Rate  
**Refresh**: 30s  
**When to Use**: System health checks, performance troubleshooting

### 2. Learning Engine
**Purpose**: Model drift detection and training monitoring  
**Key Metrics**: KL Divergence, PSI, Accuracy, Training Loss, LoRA Versions  
**Refresh**: 1m  
**When to Use**: Model quality monitoring, retraining decisions

### 3. MCP Activity
**Purpose**: MCP server monitoring  
**Key Metrics**: Calls per Server, Tool Latency, Errors, Operation Distribution  
**Refresh**: 30s  
**When to Use**: Tool server health, load balancing, error investigation

## Common Tasks

### View Current Performance
1. Open Platform Overview dashboard
2. Check P99 latency (should be < 1.5s)
3. Verify error rate (should be < 1%)
4. Monitor GPU utilization (optimal: 70-85%)

### Check Model Drift
1. Open Learning Engine dashboard
2. Check KL Divergence gauge (red if > 0.2)
3. Check PSI gauge (red if > 0.3)
4. Review accuracy trends
5. Check last training run details

### Monitor MCP Servers
1. Open MCP Activity dashboard
2. Check active servers count
3. Review latency stats (P99 < 2s)
4. Check error rates per server
5. View operation distribution

### Investigate Issues

#### High Latency
1. Platform Overview → Check P99 latency trend
2. Identify spike timing
3. Check GPU utilization at same time
4. Review queue depth
5. MCP Activity → Check if specific servers are slow

#### Errors
1. Platform Overview → Error Rate panel
2. Note affected endpoints
3. MCP Activity → MCP Errors by Server
4. Identify problematic server/operation
5. Check error rate percentage

#### Model Drift
1. Learning Engine → Check KL Divergence
2. If > 0.15, review accuracy trend
3. Check PSI for confirmation
4. Review LoRA version history
5. Check when last training occurred

## Alert Thresholds

### Critical (Immediate Action)
- ❌ Error Rate > 5%
- ❌ P99 Latency > 3s
- ❌ GPU Temperature > 85°C
- ❌ KL Divergence > 0.2

### Warning (Monitor Closely)
- ⚠️ Error Rate > 1%
- ⚠️ P99 Latency > 1.5s
- ⚠️ Cache Hit Rate < 70%
- ⚠️ PSI > 0.2

### Good (Healthy)
- ✅ Error Rate < 1%
- ✅ P99 Latency < 1s
- ✅ Cache Hit Rate > 85%
- ✅ KL Divergence < 0.1

## Troubleshooting

### Dashboard Not Loading
```bash
# Check Grafana is running
docker ps | grep grafana

# Check Grafana logs
docker logs grafana

# Restart Grafana
docker restart grafana
```

### No Data Showing
```bash
# Check Prometheus
docker ps | grep prometheus
docker logs prometheus

# Verify services are exporting metrics
curl http://localhost:8000/metrics  # API server
curl http://localhost:9090/api/v1/targets  # Prometheus targets
```

### Slow Performance
- Reduce time range (top-right picker)
- Increase refresh interval
- Use smaller time windows for detailed analysis

## Pro Tips

### Keyboard Shortcuts
- `d` + `h` = Go to home dashboard
- `f` = Toggle fullscreen for panel
- `Ctrl/Cmd` + `S` = Save dashboard
- `Esc` = Exit fullscreen

### Time Ranges
- **5m**: Real-time monitoring
- **1h**: Recent activity review
- **6h**: Shift analysis
- **24h**: Daily trends
- **7d**: Weekly patterns

### Panel Features
- **Click & Drag**: Zoom into time range
- **Double Click**: Reset zoom
- **Legend Click**: Toggle series on/off
- **Shift + Click Legend**: Solo series

## Metrics Quick Reference

### Platform
```
http_request_duration_seconds_bucket  # Request latency histogram
http_requests_total                   # Request counter
inference_tokens_total                # Token processing
cache_hits_total / cache_misses_total # Cache efficiency
DCGM_FI_DEV_GPU_UTIL                 # GPU utilization
```

### Learning Engine
```
drift_kl_divergence        # Distribution drift
drift_psi                  # Population stability
drift_current_accuracy     # Model accuracy
training_loss              # Training loss
validation_loss            # Validation loss
ewc_lambda                 # EWC regularization
lora_versions_total        # LoRA version count
```

### MCP
```
mcp_requests_total                    # MCP requests
mcp_operation_duration_seconds_bucket # Operation latency
```

## Integration Commands

### Export Dashboard
```bash
# Via API (from Grafana container)
curl -H "Authorization: Bearer <api-key>" \
  http://localhost:3000/api/dashboards/uid/platform-overview

# Via UI
Dashboard → Settings → JSON Model → Copy to clipboard
```

### Import Dashboard
```bash
# Place JSON file in configs/grafana/dashboards/
cp my-dashboard.json configs/grafana/dashboards/

# Restart Grafana or wait 10s for auto-reload
docker restart grafana
```

### Create Snapshot
```bash
# Share dashboard snapshot
Dashboard → Share → Snapshot → Create Snapshot
```

## Monitoring Schedule

### Real-time (Every 5-10 min)
- ✅ Platform Overview
- ✅ MCP Activity

### Periodic (Hourly)
- ✅ Learning Engine (quick check)
- ✅ MCP load distribution

### Daily
- ✅ Learning Engine (full review)
- ✅ Drift metrics analysis
- ✅ Training logs review

### Weekly
- ✅ Performance trends
- ✅ Resource utilization patterns
- ✅ Model quality trends
- ✅ LoRA version management

## Best Practices

1. **Set Time Range First**: Choose appropriate window for analysis
2. **Use Legends**: Toggle series to focus on specific metrics
3. **Check Related Metrics**: Cross-reference between dashboards
4. **Export Data**: Download CSV for detailed analysis
5. **Create Annotations**: Mark important events (deployments, incidents)

## Next Steps

1. **Set Up Alerts**: Configure Grafana Alerting for critical metrics
2. **Customize Dashboards**: Add panels for specific needs
3. **Create Variables**: Filter by model, server, environment
4. **Schedule Reports**: Automate dashboard PDF generation
5. **Review Documentation**: See `configs/grafana/README.md` for details

## Support

- Dashboard Documentation: `configs/grafana/README.md`
- Implementation Details: `GRAFANA_DASHBOARDS_IMPLEMENTATION.md`
- Metrics Reference: `metrics_exporter.py`, `learning_engine/metrics.py`
- Platform Architecture: `ARCHITECTURE.md`
- Observability Guide: `OBSERVABILITY_README.md`
