# Blue-Green Deployment Strategy

Comprehensive blue-green deployment implementation with automated traffic shifting, health monitoring, and rollback capabilities.

## Overview

The blue-green deployment strategy maintains two identical production environments (blue and green) to enable zero-downtime deployments with instant rollback capability.

### Key Features

- **Weighted Traffic Routing**: Gradually shift traffic from blue to green (90/10 → 50/50 → 10/90 → 0/100)
- **Automated Health Monitoring**: Continuous monitoring of error rates and P99 latency
- **Smoke Testing**: Automated smoke tests against green environment before traffic shift
- **Soak Periods**: 5-minute observation periods between traffic shifts
- **Automated Rollback**: Automatic rollback on threshold violations
- **One-Click Manual Rollback**: Instant traffic cutover back to blue
- **Prometheus Integration**: Real-time metrics collection and analysis

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Load Balancer / Ingress                   │
│                    (Weighted Traffic Routing)                    │
└─────────────────────────────────────────────────────────────────┘
                    │                           │
                    │ 90% (initially)           │ 10% (initially)
                    ▼                           ▼
        ┌───────────────────────┐   ┌───────────────────────┐
        │   Blue Environment     │   │   Green Environment    │
        │   (Current Version)    │   │   (New Version)        │
        │                        │   │                        │
        │   Service: -blue       │   │   Service: -green      │
        │   Pods: 2+             │   │   Pods: 2+             │
        │   Image: v1.0          │   │   Image: v2.0          │
        └───────────────────────┘   └───────────────────────┘
                    │                           │
                    └───────────┬───────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Backend Services     │
                    │   (Shared Resources)   │
                    │                        │
                    │   - PostgreSQL         │
                    │   - Redis              │
                    │   - Qdrant             │
                    │   - Neo4j              │
                    └────────────────────────┘
```

## Traffic Shifting Phases

### Phase 1: Deploy Green (0% traffic)
- Deploy new version to green environment
- Wait for pods to be ready
- Run smoke tests
- Duration: ~2-5 minutes

### Phase 2: 10% Canary (90% blue / 10% green)
- Shift 10% traffic to green
- Monitor for 5 minutes
- Check error rates and latency
- Rollback if thresholds exceeded

### Phase 3: 50% Split (50% blue / 50% green)
- Shift 50% traffic to green
- Monitor for 5 minutes
- Validate equal load distribution

### Phase 4: 90% Green (10% blue / 90% green)
- Shift 90% traffic to green
- Monitor for 5 minutes
- Prepare for full cutover

### Phase 5: 100% Green (0% blue / 100% green)
- Complete cutover to green
- Monitor for 1 minute
- Blue becomes new staging environment

## Configuration

### Helm Values

Enable blue-green deployment in `values.yaml`:

```yaml
blueGreen:
  enabled: true
  serviceName: agent-router
  replicaCount: 2
  
  image:
    repository: ai-platform/api-server
    blueTag: v1.0.0    # Current stable version
    greenTag: v2.0.0   # New version to deploy
  
  trafficSplit:
    blue: 90
    green: 10
  
  ingress:
    enabled: true
    className: nginx
    host: api.your-domain.com
```

### Monitoring Thresholds

Default thresholds (configurable):

- **Error Rate**: 1% (0.01)
- **P99 Latency**: 3.0 seconds
- **Soak Period**: 300 seconds (5 minutes)

## Usage

### Prerequisites

1. **Kubernetes cluster** with kubectl configured
2. **Helm 3.x** installed
3. **Prometheus** deployed and accessible
4. **NGINX Ingress Controller** with canary support
5. **Python 3.8+** with requests package

### Install/Update Helm Chart

Deploy blue-green infrastructure:

```bash
# Install with blue-green enabled
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform-prod \
  --create-namespace \
  --set blueGreen.enabled=true \
  --set blueGreen.image.blueTag=v1.0.0 \
  --set blueGreen.image.greenTag=v1.0.0

# Verify deployment
kubectl get deployments -n ai-platform-prod | grep -E "(blue|green)"
kubectl get services -n ai-platform-prod | grep -E "(blue|green)"
kubectl get ingress -n ai-platform-prod | grep -E "(blue|green)"
```

### Execute Rollout

Deploy new version using the rollout orchestrator:

```bash
cd scripts/deploy

# Dry run (recommended first)
python blue_green_rollout.py \
  --namespace ai-platform-prod \
  --service-name agent-router \
  --new-image-tag v2.0.0 \
  --prometheus-url http://prometheus.ai-platform-prod.svc.cluster.local:9090 \
  --smoke-test-url http://agent-router-green.ai-platform-prod.svc.cluster.local:8000 \
  --dry-run

# Execute actual rollout
python blue_green_rollout.py \
  --namespace ai-platform-prod \
  --service-name agent-router \
  --new-image-tag v2.0.0 \
  --prometheus-url http://prometheus.ai-platform-prod.svc.cluster.local:9090 \
  --smoke-test-url http://agent-router-green.ai-platform-prod.svc.cluster.local:8000
```

### Custom Thresholds

Adjust monitoring thresholds:

```bash
python blue_green_rollout.py \
  --namespace ai-platform-prod \
  --service-name agent-router \
  --new-image-tag v2.0.0 \
  --prometheus-url http://prometheus:9090 \
  --error-rate-threshold 0.02 \
  --p99-latency-threshold 5.0 \
  --soak-period 600
```

## Rollback

### Automatic Rollback

The orchestrator automatically rolls back if:
- Error rate exceeds threshold (default: 1%)
- P99 latency exceeds threshold (default: 3s)
- Smoke tests fail
- Green deployment fails to become ready

### Manual Rollback

#### One-Click Command

If rollout script provides the command:

```bash
kubectl annotate ingress agent-router-green-canary \
  nginx.ingress.kubernetes.io/canary-weight=0 \
  -n ai-platform-prod \
  --overwrite
```

#### Manual Steps

```bash
# 1. Set green traffic to 0%
kubectl annotate ingress agent-router-green-canary \
  nginx.ingress.kubernetes.io/canary-weight=0 \
  -n ai-platform-prod \
  --overwrite

# 2. Verify traffic is 100% blue
kubectl get ingress agent-router-green-canary -n ai-platform-prod -o yaml | grep canary-weight

# 3. Check blue environment health
kubectl get pods -n ai-platform-prod -l app.kubernetes.io/environment=blue
kubectl logs -n ai-platform-prod -l app.kubernetes.io/environment=blue --tail=100

# 4. Restore green to previous version (if needed)
kubectl set image deployment/agent-router-green \
  agent-router=ai-platform/api-server:v1.0.0 \
  -n ai-platform-prod
```

## Monitoring

### Real-Time Monitoring

Watch deployment progress:

```bash
# Monitor deployment status
kubectl rollout status deployment/agent-router-green -n ai-platform-prod -w

# Watch pods
kubectl get pods -n ai-platform-prod -l app.kubernetes.io/name=agent-router -w

# Monitor traffic split
watch 'kubectl get ingress agent-router-green-canary -n ai-platform-prod -o yaml | grep canary-weight'
```

### Prometheus Queries

Monitor health metrics:

```promql
# Error rate by environment
sum(rate(http_requests_total{environment=~"blue|green",status=~"5.."}[5m])) by (environment) 
/ 
sum(rate(http_requests_total{environment=~"blue|green"}[5m])) by (environment)

# P99 latency by environment
histogram_quantile(0.99, 
  sum(rate(http_request_duration_seconds_bucket{environment=~"blue|green"}[5m])) 
  by (le, environment)
)

# Request rate by environment
sum(rate(http_requests_total{environment=~"blue|green"}[5m])) by (environment)

# Traffic distribution
sum(rate(http_requests_total{environment="blue"}[5m])) 
/ 
(sum(rate(http_requests_total{environment="blue"}[5m])) + sum(rate(http_requests_total{environment="green"}[5m])))
```

## Grafana Dashboard

Create dashboard with panels for:

1. **Traffic Distribution** (blue vs green %)
2. **Error Rate Comparison** (blue vs green)
3. **P99 Latency Comparison** (blue vs green)
4. **Request Rate** (blue vs green)
5. **Pod Status** (ready/total by environment)
6. **Deployment Phase** (current rollout stage)

## Troubleshooting

### Green Deployment Not Ready

```bash
# Check pod status
kubectl get pods -n ai-platform-prod -l app.kubernetes.io/environment=green

# Check pod logs
kubectl logs -n ai-platform-prod -l app.kubernetes.io/environment=green --tail=100

# Describe deployment
kubectl describe deployment agent-router-green -n ai-platform-prod

# Check events
kubectl get events -n ai-platform-prod --sort-by='.lastTimestamp' | grep green
```

### Smoke Tests Failing

```bash
# Test green service directly
kubectl port-forward -n ai-platform-prod svc/agent-router-green 8000:8000

# In another terminal
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

### High Error Rate

```bash
# Check green pod logs
kubectl logs -n ai-platform-prod -l app.kubernetes.io/environment=green --tail=500 | grep -i error

# Check application metrics
curl http://agent-router-green.ai-platform-prod.svc.cluster.local:8000/metrics

# Compare with blue
kubectl logs -n ai-platform-prod -l app.kubernetes.io/environment=blue --tail=500 | grep -i error
```

### Rollback Not Working

```bash
# Force immediate rollback
kubectl annotate ingress agent-router-green-canary \
  nginx.ingress.kubernetes.io/canary-weight=0 \
  -n ai-platform-prod \
  --overwrite

# Verify
kubectl get ingress agent-router-green-canary -n ai-platform-prod -o jsonpath='{.metadata.annotations}'

# If ingress controller not responding, delete green ingress temporarily
kubectl delete ingress agent-router-green-canary -n ai-platform-prod
```

## Best Practices

1. **Always Dry Run First**: Test rollout logic without affecting production
2. **Monitor Continuously**: Watch metrics throughout deployment
3. **Keep Blue Healthy**: Don't update blue until green is proven stable
4. **Document Versions**: Tag images with semantic versions
5. **Test Rollback**: Periodically test rollback procedures
6. **Set Conservative Thresholds**: Better to rollback unnecessarily than miss issues
7. **Use Soak Periods**: Allow time for issues to manifest
8. **Log Everything**: Capture all deployment events for post-mortem
9. **Communicate**: Notify team of deployments and rollbacks
10. **Automate**: Use CI/CD pipelines to trigger rollouts

## Integration with CI/CD

### GitLab CI Example

```yaml
deploy:production:
  stage: deploy
  script:
    - python scripts/deploy/blue_green_rollout.py
        --namespace ai-platform-prod
        --service-name agent-router
        --new-image-tag $CI_COMMIT_TAG
        --prometheus-url http://prometheus:9090
        --smoke-test-url http://agent-router-green:8000
  only:
    - tags
  when: manual
```

### GitHub Actions Example

```yaml
name: Blue-Green Deploy

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBECONFIG }}
      
      - name: Deploy with Blue-Green
        run: |
          python scripts/deploy/blue_green_rollout.py \
            --namespace ai-platform-prod \
            --service-name agent-router \
            --new-image-tag ${{ github.event.release.tag_name }} \
            --prometheus-url http://prometheus:9090 \
            --smoke-test-url http://agent-router-green:8000
```

## Security Considerations

1. **RBAC**: Ensure deployment service account has minimal required permissions
2. **Network Policies**: Both environments should have same network policies
3. **Secrets**: Share secrets between blue and green environments
4. **TLS**: Ensure both environments use valid TLS certificates
5. **Audit Logging**: Log all deployment and rollback actions

## Performance Considerations

1. **Resource Limits**: Both environments should have identical resource limits
2. **Connection Pooling**: Warm up green connections before traffic shift
3. **Cache Warming**: Pre-populate caches in green environment
4. **Load Testing**: Test green environment under load before production traffic
5. **Database Connections**: Monitor connection pool saturation

## Cost Optimization

1. **Scale Down Blue**: After successful deployment, scale blue to minimum replicas
2. **Resource Requests**: Set appropriate CPU/memory requests to avoid over-provisioning
3. **Scheduled Deployments**: Deploy during off-peak hours to reduce risk
4. **Cleanup**: Remove unused resources after deployment

## Next Steps

1. **Implement A/B Testing**: Use traffic splitting for feature testing
2. **Progressive Delivery**: Extend to support phased rollouts by region/customer
3. **Automated Promotion**: Auto-promote green to blue after success period
4. **Multi-Service Rollouts**: Coordinate blue-green across multiple services
5. **Canary Analysis**: Integrate with advanced canary analysis tools

## Support

For issues or questions:
- Check logs: `kubectl logs -n ai-platform-prod -l app.kubernetes.io/name=agent-router`
- Review events: `kubectl get events -n ai-platform-prod`
- Consult documentation: See `DEPLOYMENT.md` for general deployment info
- Contact platform team: #platform-support

---

**Version**: 1.0.0  
**Last Updated**: 2025-01-01  
**Maintained by**: Platform Engineering Team
