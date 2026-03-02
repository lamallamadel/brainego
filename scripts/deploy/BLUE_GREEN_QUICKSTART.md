# Blue-Green Deployment Quick Start

Get started with blue-green deployments in 5 minutes.

## Prerequisites

```bash
# 1. Verify kubectl access
kubectl cluster-info

# 2. Verify Helm installation
helm version

# 3. Verify Python and dependencies
python3 --version
pip install requests>=2.31.0
```

## Step 1: Deploy Infrastructure (First Time)

```bash
# Deploy blue-green infrastructure
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform-prod \
  --create-namespace \
  -f helm/ai-platform/values.yaml \
  -f helm/ai-platform/values-blue-green.yaml

# Wait for deployment
kubectl rollout status deployment/agent-router-blue -n ai-platform-prod
kubectl rollout status deployment/agent-router-green -n ai-platform-prod
```

## Step 2: Verify Initial Setup

```bash
# Check deployments
kubectl get deployments -n ai-platform-prod | grep agent-router

# Check services
kubectl get services -n ai-platform-prod | grep agent-router

# Check ingress
kubectl get ingress -n ai-platform-prod | grep agent-router

# Verify traffic split (should be 90/10 initially)
kubectl get ingress agent-router-green-canary -n ai-platform-prod \
  -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}'
```

## Step 3: Deploy New Version

```bash
cd scripts/deploy

# Dry run first (recommended)
python3 blue_green_rollout.py \
  --namespace ai-platform-prod \
  --service-name agent-router \
  --new-image-tag v2.0.0 \
  --prometheus-url http://prometheus.ai-platform-prod.svc.cluster.local:9090 \
  --smoke-test-url http://agent-router-green.ai-platform-prod.svc.cluster.local:8000 \
  --dry-run

# Execute actual rollout
python3 blue_green_rollout.py \
  --namespace ai-platform-prod \
  --service-name agent-router \
  --new-image-tag v2.0.0 \
  --prometheus-url http://prometheus.ai-platform-prod.svc.cluster.local:9090 \
  --smoke-test-url http://agent-router-green.ai-platform-pod.svc.cluster.local:8000
```

## Step 4: Monitor Deployment

```bash
# Watch deployment in real-time
watch 'kubectl get pods -n ai-platform-prod -l app.kubernetes.io/name=agent-router'

# Monitor traffic split changes
watch 'kubectl get ingress agent-router-green-canary -n ai-platform-prod -o yaml | grep canary-weight'

# View rollout logs (in another terminal)
tail -f /path/to/rollout/log
```

## Step 5: Rollback (If Needed)

### Automatic Rollback
The script automatically rolls back if:
- Error rate > 1%
- P99 latency > 3s
- Smoke tests fail

### Manual Rollback
```bash
# One-click rollback script
chmod +x scripts/deploy/rollback_blue_green.sh
./scripts/deploy/rollback_blue_green.sh ai-platform-prod agent-router

# Or manual command
kubectl annotate ingress agent-router-green-canary \
  nginx.ingress.kubernetes.io/canary-weight=0 \
  -n ai-platform-prod \
  --overwrite
```

## Common Commands

### View Traffic Split
```bash
kubectl get ingress agent-router-green-canary -n ai-platform-prod \
  -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}'
```

### Check Pod Status
```bash
# Blue pods
kubectl get pods -n ai-platform-prod -l app.kubernetes.io/environment=blue

# Green pods
kubectl get pods -n ai-platform-prod -l app.kubernetes.io/environment=green
```

### View Logs
```bash
# Blue logs
kubectl logs -n ai-platform-prod -l app.kubernetes.io/environment=blue --tail=100

# Green logs
kubectl logs -n ai-platform-prod -l app.kubernetes.io/environment=green --tail=100
```

### Port Forward for Testing
```bash
# Test blue directly
kubectl port-forward -n ai-platform-prod svc/agent-router-blue 8001:8000

# Test green directly
kubectl port-forward -n ai-platform-prod svc/agent-router-green 8002:8000
```

## Deployment Timeline

```
Time    Phase           Blue %  Green % Action
--------------------------------------------------
T+0     Deploy          100%    0%      Deploy green v2.0.0
T+5     Smoke Test      100%    0%      Run smoke tests
T+7     Canary 10%      90%     10%     Shift 10% traffic
T+12    Soak Period     90%     10%     Monitor (5 min)
T+12    Split 50%       50%     50%     Shift to 50/50
T+17    Soak Period     50%     50%     Monitor (5 min)
T+17    Canary 90%      10%     90%     Shift 90% traffic
T+22    Soak Period     10%     90%     Monitor (5 min)
T+22    Complete        0%      100%    Full cutover
T+23    Final Check     0%      100%    Monitor (1 min)
T+24    Done            0%      100%    Deployment complete
```

Total deployment time: ~24 minutes (with 5-minute soak periods)

## Troubleshooting

### Deployment Stuck
```bash
# Check pod events
kubectl describe pod -n ai-platform-prod -l app.kubernetes.io/environment=green

# Check logs
kubectl logs -n ai-platform-prod -l app.kubernetes.io/environment=green --tail=200

# Check image pull
kubectl get pods -n ai-platform-prod -l app.kubernetes.io/environment=green -o jsonpath='{.items[*].status.containerStatuses[*].state}'
```

### Smoke Tests Failing
```bash
# Test green service directly
kubectl run test-pod --rm -i --tty --image=curlimages/curl -- sh
curl http://agent-router-green.ai-platform-prod.svc.cluster.local:8000/health
```

### High Latency
```bash
# Check Prometheus
kubectl port-forward -n ai-platform-prod svc/prometheus 9090:9090

# Query in browser: http://localhost:9090
# histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{environment="green"}[5m]))
```

### Rollback Not Working
```bash
# Force traffic to blue
kubectl patch ingress agent-router-green-canary -n ai-platform-prod \
  --type=json \
  -p='[{"op": "replace", "path": "/metadata/annotations/nginx.ingress.kubernetes.io~1canary-weight", "value": "0"}]'

# Verify
kubectl get ingress agent-router-green-canary -n ai-platform-prod -o yaml
```

## Next Steps

1. **Set up CI/CD integration** - See `BLUE_GREEN_DEPLOYMENT.md` for examples
2. **Create Grafana dashboards** - Monitor blue/green metrics
3. **Configure alerting** - Alert on deployment failures
4. **Document runbook** - Create team-specific procedures
5. **Test disaster recovery** - Practice rollback scenarios

## Resources

- Full documentation: `scripts/deploy/BLUE_GREEN_DEPLOYMENT.md`
- Helm chart: `helm/ai-platform/templates/blue-green-ingress.yaml`
- Rollout script: `scripts/deploy/blue_green_rollout.py`
- Values example: `helm/ai-platform/values-blue-green.yaml`

## Support

Questions or issues? Check:
1. Pod logs: `kubectl logs -n ai-platform-prod -l app.kubernetes.io/name=agent-router`
2. Events: `kubectl get events -n ai-platform-prod --sort-by='.lastTimestamp'`
3. Ingress status: `kubectl describe ingress -n ai-platform-prod`
4. Team documentation: Internal wiki/confluence

---

**Quick Reference Card**

```bash
# Deploy new version
python3 blue_green_rollout.py --namespace <ns> --service-name <svc> --new-image-tag <tag> --prometheus-url <url>

# Rollback
./rollback_blue_green.sh <namespace> <service-name>

# Check traffic
kubectl get ingress <service>-green-canary -n <ns> -o jsonpath='{.metadata.annotations}'

# View logs
kubectl logs -n <ns> -l app.kubernetes.io/environment=<blue|green> --tail=100
```
