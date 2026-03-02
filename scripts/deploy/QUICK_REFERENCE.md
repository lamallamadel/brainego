# Production Deployment - Quick Reference

## Quick Start

```bash
# 1. Install dependencies
pip install -r scripts/deploy/requirements-deploy.txt

# 2. Deploy to production
python3 scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --values-file helm/ai-platform/values-production-secure.yaml \
  --verbose

# 3. Monitor deployment
python3 scripts/deploy/monitor_deployment.py \
  --namespace ai-platform-prod \
  --watch
```

## Common Commands

### Deploy

```bash
# Standard deployment
python3 scripts/deploy/prod_deploy.py --namespace ai-platform-prod

# With smoke tests
python3 scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --smoke-test-urls https://api.example.com/health

# Dry run
python3 scripts/deploy/prod_deploy.py --namespace ai-platform-prod --dry-run
```

### Monitor

```bash
# Watch mode
python3 scripts/deploy/monitor_deployment.py --namespace ai-platform-prod --watch

# Single check
python3 scripts/deploy/monitor_deployment.py --namespace ai-platform-prod
```

### Rollback

```bash
# Interactive rollback
bash scripts/deploy/rollback.sh

# Specify revision
TARGET_REVISION=1 bash scripts/deploy/rollback.sh
```

### Smoke Tests

```bash
# Run smoke tests
python3 scripts/deploy/smoke_tests.py --base-url https://api.example.com
```

## Helm Commands

```bash
# List releases
helm list -n ai-platform-prod

# Status
helm status ai-platform -n ai-platform-prod

# History
helm history ai-platform -n ai-platform-prod

# Test
helm test ai-platform -n ai-platform-prod

# Rollback
helm rollback ai-platform -n ai-platform-prod

# Uninstall
helm uninstall ai-platform -n ai-platform-prod
```

## Kubectl Commands

```bash
# Get all resources
kubectl get all -n ai-platform-prod

# Get pods
kubectl get pods -n ai-platform-prod

# Watch pods
kubectl get pods -n ai-platform-prod -w

# Describe pod
kubectl describe pod <pod-name> -n ai-platform-prod

# Logs
kubectl logs <pod-name> -n ai-platform-prod

# Follow logs
kubectl logs -f <pod-name> -n ai-platform-prod

# Get StatefulSets
kubectl get statefulset -n ai-platform-prod

# Get PVCs
kubectl get pvc -n ai-platform-prod

# Get services
kubectl get svc -n ai-platform-prod

# Get ingress
kubectl get ingress -n ai-platform-prod

# Get network policies
kubectl get networkpolicy -n ai-platform-prod

# Get events
kubectl get events -n ai-platform-prod --sort-by='.lastTimestamp'
```

## Verification Commands

```bash
# Check pod status
kubectl get pods -n ai-platform-prod -o wide

# Check StatefulSet status
kubectl get statefulset -n ai-platform-prod -o json | \
  jq -r '.items[] | "\(.metadata.name): \(.status.readyReplicas)/\(.spec.replicas)"'

# Check PVC status
kubectl get pvc -n ai-platform-prod -o json | \
  jq -r '.items[] | "\(.metadata.name): \(.status.phase)"'

# Check certificate status
kubectl get certificate -n ai-platform-prod

# Check Ingress
kubectl describe ingress ai-platform-ingress -n ai-platform-prod
```

## Health Checks

```bash
# Gateway
curl https://api.example.com/gateway/health

# Agent Router
curl https://api.example.com/v1/health

# Memory Service
curl https://api.example.com/memory/health

# Learning Engine
curl https://api.example.com/learning/health

# MCP Gateway
curl https://api.example.com/mcp/health

# Metrics
curl https://api.example.com/metrics
```

## Troubleshooting

### Pod not starting

```bash
kubectl describe pod <pod-name> -n ai-platform-prod
kubectl logs <pod-name> -n ai-platform-prod
kubectl get events -n ai-platform-prod | grep <pod-name>
```

### StatefulSet not ready

```bash
kubectl get statefulset <name> -n ai-platform-prod -o yaml
kubectl describe statefulset <name> -n ai-platform-prod
kubectl logs <name>-0 -n ai-platform-prod
```

### PVC not bound

```bash
kubectl describe pvc <pvc-name> -n ai-platform-prod
kubectl get pv
kubectl get storageclass
```

### Ingress issues

```bash
kubectl describe ingress ai-platform-ingress -n ai-platform-prod
kubectl get certificate -n ai-platform-prod
kubectl logs -n cert-manager -l app=cert-manager
```

## Port Forwarding

```bash
# Grafana
kubectl port-forward -n ai-platform-prod svc/grafana 3000:3000

# Prometheus
kubectl port-forward -n ai-platform-prod svc/prometheus 9090:9090

# Agent Router
kubectl port-forward -n ai-platform-prod svc/agent-router 8000:8000

# Gateway
kubectl port-forward -n ai-platform-prod svc/gateway 9002:9002
```

## Environment Variables

```bash
export NAMESPACE="ai-platform-prod"
export RELEASE_NAME="ai-platform"
export BASE_URL="https://api.example.com"
export KUBECONFIG="/path/to/kubeconfig"
```

## Files

- `scripts/deploy/prod_deploy.py` - Main deployment script
- `scripts/deploy/smoke_tests.py` - Smoke test runner
- `scripts/deploy/monitor_deployment.py` - Status monitor
- `scripts/deploy/deploy_example.sh` - Deployment example
- `scripts/deploy/rollback.sh` - Rollback script
- `scripts/deploy/DEPLOYMENT_GUIDE.md` - Full guide
- `scripts/deploy/DEPLOYMENT_CHECKLIST.md` - Checklist

## Exit Codes

- `0` - Success
- `1` - Failure

## Log Files

- `prod_deploy_YYYYMMDD_HHMMSS.log` - Deployment logs

## Dependencies

```bash
pip install pyyaml>=6.0.1
pip install kubernetes>=28.1.0
pip install requests>=2.31.0
```

## Support

- Check log files
- Review Kubernetes events
- Consult DEPLOYMENT_GUIDE.md
- Contact platform team
