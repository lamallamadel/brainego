# Observability Stack - Deployment Checklist

## Pre-Deployment

### Infrastructure
- [ ] Docker and Docker Compose installed
- [ ] NVIDIA GPU drivers installed (for GPU metrics)
- [ ] Sufficient disk space (10GB+ recommended)
- [ ] Network ports available (9090, 3000, 3100, 9093, etc.)

### Configuration
- [ ] Copy `.env.observability.example` to `.env.observability`
- [ ] Set `SLACK_WEBHOOK_URL` in `.env.observability`
- [ ] Create Slack channels:
  - [ ] #ai-platform-alerts
  - [ ] #ai-platform-critical
  - [ ] #ai-platform-gpu
  - [ ] #ai-platform-drift
  - [ ] #ai-platform-budget
  - [ ] #ai-platform-infra
- [ ] Review alert thresholds in `configs/prometheus/rules/alerts.yml`
- [ ] Review retention settings (90 days default)

## Deployment

### Start Services
- [ ] Run `chmod +x start_observability.sh test_observability.sh`
- [ ] Run `./start_observability.sh`
- [ ] Wait for all services to be healthy (30-60 seconds)

### Verify Deployment
- [ ] Run `./test_observability.sh`
- [ ] Check all tests pass
- [ ] Verify Prometheus targets: http://localhost:9090/targets
- [ ] All targets should show "up" status
- [ ] Check Grafana: http://localhost:3000 (admin/admin)
- [ ] Verify Loki: http://localhost:3100/ready
- [ ] Check Jaeger: http://localhost:16686
- [ ] Verify AlertManager: http://localhost:9093

### Test Metrics
- [ ] Gateway metrics: http://localhost:9002/metrics
- [ ] MCPJungle metrics: http://localhost:9100/metrics
- [ ] API Server metrics: http://localhost:8000/metrics
- [ ] MAX Serve metrics: http://localhost:8080/metrics
- [ ] Prometheus self-metrics: http://localhost:9090/metrics

### Test Logs
- [ ] Query Loki: `curl -G "http://localhost:3100/loki/api/v1/query" --data-urlencode 'query={job="gateway"}'`
- [ ] Check Promtail is scraping logs
- [ ] Verify JSON parsing working
- [ ] Test log search in Grafana Explore

### Test Traces
- [ ] Send test request through gateway
- [ ] Check trace appears in Jaeger UI
- [ ] Verify trace spans include all services
- [ ] Confirm trace context in logs

### Test Alerts
- [ ] Verify alert rules loaded in Prometheus
- [ ] Check AlertManager configuration
- [ ] Trigger test alert (optional)
- [ ] Verify Slack webhook (send test)

## Integration

### Add Metrics to Services
For each service:
- [ ] Import `metrics_exporter.py`
- [ ] Initialize metrics: `metrics = get_metrics_exporter('service-name')`
- [ ] Add `/metrics` endpoint
- [ ] Record metrics for operations
- [ ] Test metrics endpoint works

### Add Structured Logging
For each service:
- [ ] Import `structured_logger.py`
- [ ] Setup logging: `setup_structured_logging('service-name')`
- [ ] Replace logging calls with structured logger
- [ ] Add service-specific fields
- [ ] Test logs appear in Loki

### Configure Tracing
For each service:
- [ ] Set `OTLP_ENDPOINT=http://otel-collector:4317`
- [ ] Set `ENABLE_TELEMETRY=true`
- [ ] Configure OpenTelemetry instrumentation
- [ ] Test traces appear in Jaeger

## Post-Deployment

### Grafana Setup
- [ ] Login to Grafana (admin/admin)
- [ ] Change admin password
- [ ] Add Prometheus data source
- [ ] Add Loki data source
- [ ] Import/create dashboards
- [ ] Test dashboard queries
- [ ] Configure user access

### AlertManager Setup
- [ ] Verify Slack integration working
- [ ] Test alert notifications
- [ ] Configure alert routing rules
- [ ] Set up alert silences (if needed)
- [ ] Document on-call procedures

### Monitoring
- [ ] Create runbooks for common alerts
- [ ] Document metric meanings
- [ ] Set up dashboard rotation
- [ ] Configure alert escalation
- [ ] Schedule regular reviews

### Backup
- [ ] Configure backup for Prometheus data
- [ ] Configure backup for Loki data
- [ ] Configure backup for Grafana dashboards
- [ ] Test restore procedures
- [ ] Document backup locations

### Security
- [ ] Change default Grafana password
- [ ] Enable authentication on Prometheus (production)
- [ ] Configure TLS for external access
- [ ] Restrict network access to dashboards
- [ ] Rotate Slack webhook URLs
- [ ] Review RBAC settings

## Validation

### Metrics Validation
- [ ] All services reporting metrics
- [ ] Metrics have correct labels
- [ ] Histograms have proper buckets
- [ ] Counters are incrementing
- [ ] Gauges show current values
- [ ] No missing metrics

### Logs Validation
- [ ] All services writing JSON logs
- [ ] Logs include trace context
- [ ] Labels extracted correctly
- [ ] Timestamps are accurate
- [ ] No parsing errors
- [ ] Log volume is reasonable

### Traces Validation
- [ ] Full request path traced
- [ ] Spans have correct attributes
- [ ] Parent-child relationships correct
- [ ] Trace sampling working
- [ ] No missing spans
- [ ] Latency attribution accurate

### Alerts Validation
- [ ] Alert rules evaluating correctly
- [ ] Alert thresholds appropriate
- [ ] Alert descriptions clear
- [ ] Slack notifications working
- [ ] Alert routing correct
- [ ] Silences working

## Performance

### Resource Usage
- [ ] Check Prometheus memory usage
- [ ] Check Loki disk usage
- [ ] Monitor OTel Collector CPU
- [ ] Verify scrape intervals
- [ ] Check query performance
- [ ] Monitor data retention

### Optimization
- [ ] Tune scrape intervals if needed
- [ ] Adjust retention periods
- [ ] Configure recording rules
- [ ] Optimize dashboard queries
- [ ] Review cardinality
- [ ] Implement down sampling

## Documentation

### Internal Docs
- [ ] Document metric meanings
- [ ] Create alert runbooks
- [ ] Document query examples
- [ ] Create troubleshooting guide
- [ ] Document configuration
- [ ] Record architectural decisions

### Team Training
- [ ] Train team on Grafana
- [ ] Train on Prometheus queries
- [ ] Train on Loki queries
- [ ] Train on Jaeger traces
- [ ] Train on alert response
- [ ] Schedule knowledge sharing

## Maintenance

### Regular Tasks
- [ ] Review alert rules monthly
- [ ] Check disk usage weekly
- [ ] Validate backups weekly
- [ ] Update dashboards as needed
- [ ] Review metric cardinality
- [ ] Check for service upgrades

### Incident Response
- [ ] Document alert handling
- [ ] Create escalation procedures
- [ ] Test alert notifications
- [ ] Practice incident response
- [ ] Review post-mortems
- [ ] Update runbooks

## Success Criteria

- [ ] ✅ All services reporting metrics
- [ ] ✅ All logs appearing in Loki
- [ ] ✅ Traces visible for requests
- [ ] ✅ Alerts configured and firing correctly
- [ ] ✅ Dashboards showing data
- [ ] ✅ Team trained on tools
- [ ] ✅ Documentation complete
- [ ] ✅ Backup procedures tested
- [ ] ✅ Security measures in place
- [ ] ✅ Performance acceptable

## Troubleshooting

### Common Issues

**Metrics not appearing:**
- [ ] Check service `/metrics` endpoint
- [ ] Verify Prometheus target is up
- [ ] Check network connectivity
- [ ] Review Prometheus logs

**Logs not appearing:**
- [ ] Check Promtail is running
- [ ] Verify Docker socket access
- [ ] Check Loki is receiving logs
- [ ] Review log format

**Traces not appearing:**
- [ ] Verify OTLP endpoint configured
- [ ] Check OTel Collector logs
- [ ] Verify Jaeger is running
- [ ] Check trace sampling

**Alerts not firing:**
- [ ] Verify alert rules loaded
- [ ] Check AlertManager configuration
- [ ] Verify Slack webhook URL
- [ ] Check alert evaluation

## Sign-off

### Deployment Team
- [ ] Infrastructure team sign-off
- [ ] Development team sign-off
- [ ] Operations team sign-off
- [ ] Security team sign-off

### Production Readiness
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Team trained
- [ ] Backup tested
- [ ] Security reviewed
- [ ] Performance validated

### Go-Live
- [ ] Communication plan executed
- [ ] Monitoring confirmed
- [ ] On-call schedule updated
- [ ] Rollback plan ready
- [ ] Post-deployment review scheduled

---

**Deployment Date:** _______________
**Deployed By:** _______________
**Reviewed By:** _______________
**Approved By:** _______________
