# Production Deployment Guide

Complete guide for deploying the AI Platform to production using the automated deployment scripts.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Pre-Deployment Setup](#pre-deployment-setup)
4. [Deployment Process](#deployment-process)
5. [Post-Deployment Verification](#post-deployment-verification)
6. [Monitoring](#monitoring)
7. [Rollback Procedure](#rollback-procedure)
8. [Troubleshooting](#troubleshooting)

## Overview

The production deployment automation provides:

- **Automated Helm chart deployment** with validation
- **Kong Ingress** configuration with TLS cert-manager integration
- **Network policies** and RBAC security
- **StatefulSet** readiness verification (Postgres, Qdrant, Neo4j, Redis)
- **PVC mount** validation
- **Helm tests** execution
- **Smoke tests** against production URLs
- **Comprehensive logging** and reporting

## Prerequisites

### System Requirements

```bash
# Kubernetes cluster
- Kubernetes 1.24+
- kubectl configured with cluster access
- Sufficient cluster resources (CPU, Memory, Storage)

# Tools
- Helm 3.x
- kubectl
- Python 3.8+
- jq (for monitoring scripts)

# Python packages
pip install -r scripts/deploy/requirements-deploy.txt
```

### Cluster Preparation

```bash
# 1. Create namespace (or let script create it)
kubectl create namespace ai-platform-prod

# 2. Create secrets
kubectl create secret generic postgres-credentials \
  --from-literal=username=postgres \
  --from-literal=password=<secure-password> \
  -n ai-platform-prod

kubectl create secret generic neo4j-credentials \
  --from-literal=username=neo4j \
  --from-literal=password=<secure-password> \
  -n ai-platform-prod

# 3. Install cert-manager (if not already installed)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml

# 4. Install Kong (if not already installed)
helm repo add kong https://charts.konghq.com
helm install kong kong/kong -n kong-system --create-namespace
```

### Configuration Files

Ensure these files are configured:

- `helm/ai-platform/values-production-secure.yaml` - Production values
- `helm/ai-platform/Chart.yaml` - Chart metadata
- `helm/ai-platform/templates/*` - All templates

## Pre-Deployment Setup

### 1. Review Configuration

```bash
# Review production values
cat helm/ai-platform/values-production-secure.yaml

# Key settings to verify:
# - namespace.name
# - kong.enabled=true
# - certManager.enabled=true
# - networkPolicies.enabled=true
# - rbac.enabled=true
# - Resource limits
# - Replica counts
# - Storage sizes
# - Domain names
```

### 2. Validate Chart

```bash
# Lint the chart
helm lint helm/ai-platform -f helm/ai-platform/values-production-secure.yaml

# Template the chart to verify
helm template ai-platform helm/ai-platform \
  -f helm/ai-platform/values-production-secure.yaml \
  --namespace ai-platform-prod \
  > /tmp/rendered-chart.yaml

# Review rendered output
less /tmp/rendered-chart.yaml
```

### 3. Dry Run

```bash
# Test deployment without applying changes
python3 scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --dry-run \
  --verbose
```

## Deployment Process

### Option 1: Automated Deployment (Recommended)

Use the provided deployment script:

```bash
# Set environment variables
export NAMESPACE="ai-platform-prod"
export RELEASE_NAME="ai-platform"
export BASE_URL="https://api.example.com"

# Run deployment
bash scripts/deploy/deploy_example.sh
```

### Option 2: Manual Deployment with prod_deploy.py

```bash
python3 scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --release-name ai-platform \
  --chart-path helm/ai-platform \
  --values-file helm/ai-platform/values-production-secure.yaml \
  --timeout 600 \
  --helm-extra-args \
    --set kong.enabled=true \
    --set certManager.enabled=true \
  --smoke-test-urls \
    https://api.example.com/health \
    https://api.example.com/metrics \
  --verbose
```

### Option 3: Standard Helm Deployment

```bash
helm upgrade --install ai-platform helm/ai-platform \
  --namespace ai-platform-prod \
  --create-namespace \
  -f helm/ai-platform/values-production-secure.yaml \
  --wait \
  --timeout 10m
```

### Deployment Phases

The deployment process consists of:

1. **Pre-deployment Validation** (2-3 minutes)
   - Prerequisites check
   - Chart validation
   - Kong Ingress validation
   - Cert-manager validation

2. **Namespace Setup** (< 1 minute)
   - Namespace creation
   - Labels application

3. **Helm Deployment** (5-10 minutes)
   - Chart deployment
   - Resource creation
   - Waiting for readiness

4. **Post-deployment Verification** (3-5 minutes)
   - Network policies check
   - RBAC verification
   - Pod status verification
   - StatefulSet readiness
   - PVC mount verification

5. **Testing** (2-3 minutes)
   - Helm tests
   - Smoke tests

Total time: **15-25 minutes**

## Post-Deployment Verification

### 1. Check Deployment Status

```bash
# Get Helm release status
helm status ai-platform -n ai-platform-prod

# List all releases
helm list -n ai-platform-prod

# View release history
helm history ai-platform -n ai-platform-prod
```

### 2. Verify Pods

```bash
# Check pod status
kubectl get pods -n ai-platform-prod

# Check for failed pods
kubectl get pods -n ai-platform-prod --field-selector=status.phase!=Running

# Watch pod status
kubectl get pods -n ai-platform-prod -w
```

### 3. Verify StatefulSets

```bash
# Check all StatefulSets
kubectl get statefulset -n ai-platform-prod

# Check specific StatefulSet
kubectl get statefulset postgres -n ai-platform-prod -o wide

# Verify replicas are ready
kubectl get statefulset -n ai-platform-prod -o json | \
  jq -r '.items[] | "\(.metadata.name): \(.status.readyReplicas)/\(.spec.replicas)"'
```

### 4. Verify PVCs

```bash
# Check all PVCs
kubectl get pvc -n ai-platform-prod

# Check PVC status
kubectl get pvc -n ai-platform-prod -o json | \
  jq -r '.items[] | "\(.metadata.name): \(.status.phase)"'
```

### 5. Verify Services

```bash
# List all services
kubectl get svc -n ai-platform-prod

# Check LoadBalancer external IP (if applicable)
kubectl get svc -n ai-platform-prod -o wide
```

### 6. Verify Ingress

```bash
# Check Ingress resources
kubectl get ingress -n ai-platform-prod

# Check Ingress details
kubectl describe ingress ai-platform-ingress -n ai-platform-prod
```

### 7. Verify TLS Certificates

```bash
# Check cert-manager certificates
kubectl get certificate -n ai-platform-prod

# Check certificate details
kubectl describe certificate ai-platform-tls -n ai-platform-prod

# Verify certificate is Ready
kubectl get certificate ai-platform-tls -n ai-platform-prod -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
```

### 8. Test Endpoints

```bash
# Health checks
curl -k https://api.example.com/gateway/health
curl -k https://api.example.com/v1/health
curl -k https://api.example.com/memory/health
curl -k https://api.example.com/learning/health
curl -k https://api.example.com/mcp/health

# Metrics
curl -k https://api.example.com/metrics
```

### 9. Run Smoke Tests

```bash
python3 scripts/deploy/smoke_tests.py \
  --base-url https://api.example.com \
  --retry-count 3 \
  --retry-delay 10
```

## Monitoring

### Real-time Monitoring

```bash
# Use the monitoring script
python3 scripts/deploy/monitor_deployment.py \
  --namespace ai-platform-prod \
  --watch \
  --interval 5
```

### Manual Monitoring

```bash
# Watch pod status
watch kubectl get pods -n ai-platform-prod

# Watch events
kubectl get events -n ai-platform-prod --watch

# Stream logs
kubectl logs -n ai-platform-prod -l app.kubernetes.io/name=agent-router -f
```

### Grafana Dashboards

```bash
# Port-forward to Grafana
kubectl port-forward -n ai-platform-prod svc/grafana 3000:3000

# Access at: http://localhost:3000
# Default credentials: admin / <from secret>
```

### Prometheus Metrics

```bash
# Port-forward to Prometheus
kubectl port-forward -n ai-platform-prod svc/prometheus 9090:9090

# Access at: http://localhost:9090
```

## Rollback Procedure

### When to Rollback

Consider rollback if:
- Critical bugs detected
- Performance degradation
- Data corruption risk
- Security vulnerabilities
- High error rates
- Service unavailability

### Automated Rollback

```bash
# Use the rollback script
bash scripts/deploy/rollback.sh

# Or specify target revision
TARGET_REVISION=1 bash scripts/deploy/rollback.sh
```

### Manual Rollback

```bash
# Rollback to previous revision
helm rollback ai-platform -n ai-platform-prod --wait

# Rollback to specific revision
helm rollback ai-platform 2 -n ai-platform-prod --wait

# Check rollback status
helm status ai-platform -n ai-platform-prod
```

### Post-Rollback Verification

```bash
# Verify pods are running
kubectl get pods -n ai-platform-prod

# Check StatefulSets
kubectl get statefulset -n ai-platform-prod

# Test endpoints
curl -k https://api.example.com/health
```

## Troubleshooting

### Pod Not Starting

```bash
# Describe pod
kubectl describe pod <pod-name> -n ai-platform-prod

# Check logs
kubectl logs <pod-name> -n ai-platform-prod

# Check events
kubectl get events -n ai-platform-prod --sort-by='.lastTimestamp' | grep <pod-name>
```

### StatefulSet Not Ready

```bash
# Check StatefulSet status
kubectl get statefulset <name> -n ai-platform-prod -o yaml

# Check PVCs
kubectl get pvc -n ai-platform-prod -l app.kubernetes.io/name=<name>

# Check pod logs
kubectl logs <name>-0 -n ai-platform-prod
```

### PVC Not Bound

```bash
# Check PVC status
kubectl describe pvc <pvc-name> -n ai-platform-prod

# Check storage class
kubectl get storageclass

# Check PV availability
kubectl get pv
```

### Ingress Not Working

```bash
# Check Ingress
kubectl describe ingress ai-platform-ingress -n ai-platform-prod

# Check Kong pods
kubectl get pods -n kong-system

# Check cert-manager
kubectl get certificate -n ai-platform-prod
kubectl describe certificate ai-platform-tls -n ai-platform-prod
```

### TLS Certificate Issues

```bash
# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager

# Check certificate request
kubectl get certificaterequest -n ai-platform-prod

# Check ACME challenge
kubectl get challenge -n ai-platform-prod
```

### Network Policy Issues

```bash
# Check network policies
kubectl get networkpolicy -n ai-platform-prod

# Describe specific policy
kubectl describe networkpolicy <policy-name> -n ai-platform-prod

# Test connectivity from a pod
kubectl exec -it <pod-name> -n ai-platform-prod -- wget -O- <url>
```

### Resource Issues

```bash
# Check node resources
kubectl top nodes

# Check pod resources
kubectl top pods -n ai-platform-prod

# Check resource quotas
kubectl get resourcequota -n ai-platform-prod
```

## Best Practices

1. **Always test in staging first**
2. **Use dry-run before actual deployment**
3. **Keep values files in version control**
4. **Tag releases in git**
5. **Monitor deployment for 24 hours**
6. **Document any issues or deviations**
7. **Have rollback plan ready**
8. **Notify team before and after deployment**
9. **Schedule deployments during low-traffic periods**
10. **Keep backups of databases before deployment**

## Support

For issues or questions:
- Check logs: `scripts/deploy/prod_deploy_*.log`
- Review Kubernetes events
- Check Grafana dashboards
- Consult team documentation

## References

- [Helm Documentation](https://helm.sh/docs/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Kong Ingress Controller](https://docs.konghq.com/kubernetes-ingress-controller/)
- [Cert-Manager Documentation](https://cert-manager.io/docs/)
