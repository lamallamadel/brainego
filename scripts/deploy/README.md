# Production Deployment Automation

This directory contains scripts for automated production deployment of the AI Platform Helm chart.

## Overview

The `prod_deploy.py` script orchestrates the complete production deployment workflow:

1. **Pre-deployment Validation**
   - Verify prerequisites (helm, kubectl)
   - Validate Helm chart syntax
   - Validate Kong Ingress configuration
   - Validate TLS cert-manager integration

2. **Deployment**
   - Create/verify namespace
   - Deploy Helm chart with production values
   - Apply network policies
   - Apply RBAC configurations

3. **Post-deployment Verification**
   - Verify pod status
   - Verify StatefulSet readiness (Postgres, Qdrant, Neo4j, Redis)
   - Verify PVC mounts
   - Run Helm tests
   - Execute smoke tests

## Prerequisites

```bash
# Python packages (add to requirements-deploy.txt)
pip install pyyaml>=6.0.1
pip install kubernetes>=28.1.0
pip install requests>=2.31.0

# Required tools
- helm (v3.x)
- kubectl
- Access to Kubernetes cluster
```

## Usage

### Basic Production Deployment

```bash
python scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --release-name ai-platform \
  --chart-path helm/ai-platform \
  --values-file helm/ai-platform/values-production-secure.yaml
```

### With Smoke Tests

```bash
python scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --smoke-test-urls \
    https://api.example.com/health \
    https://api.example.com/v1/chat/completions
```

### Dry Run

```bash
python scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --dry-run
```

### With Custom Helm Arguments

```bash
python scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --helm-extra-args \
    --set kong.enabled=true \
    --set certManager.enabled=true \
    --set networkPolicies.enabled=true
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--namespace` | Kubernetes namespace | `ai-platform-prod` |
| `--release-name` | Helm release name | `ai-platform` |
| `--chart-path` | Path to Helm chart | `helm/ai-platform` |
| `--values-file` | Production values file | `values-production-secure.yaml` |
| `--timeout` | Timeout in seconds | `600` |
| `--kubeconfig` | Path to kubeconfig | Use default |
| `--helm-extra-args` | Extra Helm arguments | `[]` |
| `--smoke-test-urls` | URLs for smoke tests | `[]` |
| `--skip-tests` | Skip Helm tests | `false` |
| `--skip-smoke-tests` | Skip smoke tests | `false` |
| `--dry-run` | Dry run mode | `false` |
| `--verbose` | Enable verbose logging | `false` |

## Deployment Phases

### Phase 1: Pre-deployment Validation

The script validates:
- Helm and kubectl are installed and accessible
- Chart path exists and is valid
- Values file exists
- Cluster connectivity
- Chart syntax (helm lint)
- Template rendering (helm template)
- Kong Ingress configuration
- TLS cert-manager setup

### Phase 2: Namespace Setup

- Creates namespace if it doesn't exist
- Applies production labels
- Prepares for deployment

### Phase 3: Helm Deployment

- Executes `helm upgrade --install` with production values
- Waits for resources to be ready
- Applies timeout safeguards

### Phase 4: Post-deployment Verification

#### Network Policies
- Lists all network policies in namespace
- Verifies expected policies exist

#### RBAC
- Verifies ServiceAccounts are created
- Verifies Roles are created
- Verifies RoleBindings are created

#### Pod Status
- Lists all pods
- Counts running vs failed pods
- Logs any failures

#### StatefulSets
- Checks Postgres StatefulSet
- Checks Qdrant StatefulSet
- Checks Neo4j StatefulSet
- Checks Redis StatefulSet
- Verifies replica counts
- Waits for all to be ready (5 min timeout)

#### PVC Mounts
- Lists all PVCs
- Verifies PVCs are bound
- Checks mount status

### Phase 5: Testing

#### Helm Tests
- Executes `helm test` if available
- Logs test results

#### Smoke Tests
- HTTP GET requests to provided URLs
- Verifies 200 status codes
- Reports success/failure counts

### Phase 6: Report

- Generates deployment summary
- Shows release status
- Reports duration
- Outputs to log file

## Validation Details

### Kong Ingress Validation

The script validates:
- TLS configuration exists
- TLS secret names are specified
- Cert-manager annotations present (`cert-manager.io/cluster-issuer`)
- Kong plugin annotations present (`konghq.com/plugins`)
- ACME challenge type configured

### Cert-Manager Validation

The script validates:
- ClusterIssuers are defined
- ACME configuration (email, server)
- Certificate resources exist
- DNS names are configured

### StatefulSet Verification

For each StatefulSet (Postgres, Qdrant, Neo4j, Redis):
- Checks if deployed
- Verifies desired vs ready replicas
- Validates PVC templates
- Confirms PVCs are created and bound
- Waits for all replicas to be ready

## Logging

Logs are written to:
- Console (stdout)
- File: `prod_deploy_YYYYMMDD_HHMMSS.log`

Log levels:
- INFO: Standard deployment progress
- WARNING: Non-critical issues
- ERROR: Deployment failures
- DEBUG: Detailed output (use `--verbose`)

## Error Handling

The script raises `DeploymentError` for:
- Missing prerequisites
- Chart validation failures
- Deployment failures
- Verification failures

Exit codes:
- `0`: Success
- `1`: Failure

## Examples

### Minimal Production Deployment

```bash
python scripts/deploy/prod_deploy.py
```

### Full Production Deployment with All Validations

```bash
python scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --release-name ai-platform \
  --values-file helm/ai-platform/values-production-secure.yaml \
  --smoke-test-urls \
    https://api.prod.example.com/health \
    https://api.prod.example.com/metrics \
  --verbose
```

### Staging Environment Deployment

```bash
python scripts/deploy/prod_deploy.py \
  --namespace ai-platform-staging \
  --release-name ai-platform-staging \
  --values-file helm/ai-platform/values-staging.yaml \
  --helm-extra-args \
    --set replicaCount=1 \
    --set resources.limits.memory=2Gi
```

### Dry Run for Testing

```bash
python scripts/deploy/prod_deploy.py \
  --namespace ai-platform-prod \
  --dry-run \
  --verbose
```

## Troubleshooting

### Helm Not Found

```bash
# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

### Kubectl Not Found

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
```

### Cluster Connectivity Issues

```bash
# Verify kubeconfig
export KUBECONFIG=/path/to/kubeconfig
kubectl cluster-info

# Or specify in command
python scripts/deploy/prod_deploy.py --kubeconfig /path/to/kubeconfig
```

### StatefulSet Not Ready

```bash
# Check StatefulSet status
kubectl get statefulset -n ai-platform-prod

# Check pod logs
kubectl logs -n ai-platform-prod postgres-0

# Describe StatefulSet
kubectl describe statefulset -n ai-platform-prod postgres
```

### PVC Not Bound

```bash
# Check PVC status
kubectl get pvc -n ai-platform-prod

# Check storage class
kubectl get storageclass

# Describe PVC
kubectl describe pvc -n ai-platform-prod postgres-data-postgres-0
```

## Security Considerations

1. **Secrets Management**: Never commit secrets to version control
2. **RBAC**: Script verifies least-privilege RBAC is applied
3. **Network Policies**: Script verifies network isolation
4. **TLS**: Script validates TLS configuration
5. **Image Security**: Use production-secure values file

## CI/CD Integration

### GitHub Actions

```yaml
- name: Deploy to Production
  run: |
    python scripts/deploy/prod_deploy.py \
      --namespace ai-platform-prod \
      --kubeconfig ${{ secrets.KUBECONFIG }} \
      --smoke-test-urls https://api.prod.example.com/health
```

### GitLab CI

```yaml
deploy:production:
  script:
    - python scripts/deploy/prod_deploy.py --namespace ai-platform-prod
  only:
    - main
```

## Monitoring

After deployment, monitor:
- Prometheus metrics: `https://prometheus.example.com`
- Grafana dashboards: `https://grafana.example.com`
- Jaeger traces: `https://jaeger.example.com`
- Kubernetes events: `kubectl get events -n ai-platform-prod`

## Rollback

If deployment fails:

```bash
# Rollback Helm release
helm rollback ai-platform -n ai-platform-prod

# Or rollback to specific revision
helm rollback ai-platform 1 -n ai-platform-prod
```
