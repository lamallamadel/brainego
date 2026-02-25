# Kubernetes Security Quick Start Guide

This guide provides quick commands to deploy and verify the AI Platform with comprehensive security features.

## Prerequisites

- Kubernetes cluster 1.21+
- kubectl configured with admin access
- Helm 3.x installed

## Quick Deployment

### 1. Deploy with Default Security Settings

```bash
# Generate encryption key
ENCRYPTION_KEY=$(head -c 32 /dev/urandom | base64)

# Install with security enabled
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace \
  --set networkPolicies.enabled=true \
  --set rbac.enabled=true \
  --set secrets.encryption.enabled=true \
  --set secrets.encryption.provider=aesgcm \
  --set secrets.encryption.aesgcm.key="$ENCRYPTION_KEY"
```

### 2. Configure Secrets Encryption at Rest

```bash
# Extract encryption configuration
kubectl get configmap secrets-encryption-config -n ai-platform \
  -o jsonpath='{.data.encryption-config\.yaml}' > /tmp/encryption-config.yaml

# On master node:
sudo mkdir -p /etc/kubernetes/enc
sudo cp /tmp/encryption-config.yaml /etc/kubernetes/enc/
sudo chmod 600 /etc/kubernetes/enc/encryption-config.yaml
sudo chown root:root /etc/kubernetes/enc/encryption-config.yaml

# Edit kube-apiserver manifest
sudo vi /etc/kubernetes/manifests/kube-apiserver.yaml
```

Add to kube-apiserver command:
```yaml
- --encryption-provider-config=/etc/kubernetes/enc/encryption-config.yaml
```

Add volume mount:
```yaml
volumeMounts:
- name: enc
  mountPath: /etc/kubernetes/enc
  readOnly: true

volumes:
- name: enc
  hostPath:
    path: /etc/kubernetes/enc
    type: DirectoryOrCreate
```

Wait for kube-apiserver to restart, then:
```bash
# Re-encrypt all secrets
kubectl get secrets --all-namespaces -o json | kubectl replace -f -
```

## Quick Verification

### Network Policies

```bash
# List all network policies
kubectl get networkpolicies -n ai-platform

# Expected output: ~15 network policies
# - default-deny-all-ingress
# - default-deny-all-egress
# - allow-dns-access
# - gateway-network-policy
# - agent-router-network-policy
# - max-serve-llama-network-policy
# - max-serve-qwen-network-policy
# - max-serve-deepseek-network-policy
# - learning-engine-network-policy
# - mem0-network-policy
# - qdrant-network-policy
# - redis-network-policy
# - postgres-network-policy
# - neo4j-network-policy
# - minio-network-policy
# - jaeger-network-policy
# - prometheus-network-policy
# - grafana-network-policy
```

### RBAC

```bash
# List all service accounts
kubectl get serviceaccounts -n ai-platform

# Expected output: ~15 service accounts
# - gateway-sa
# - agent-router-sa
# - mcpjungle-sa
# - max-serve-llama-sa
# - max-serve-qwen-sa
# - max-serve-deepseek-sa
# - learning-engine-sa
# - mem0-sa
# - postgres-sa
# - redis-sa
# - qdrant-sa
# - neo4j-sa
# - minio-sa
# - prometheus-sa
# - grafana-sa
# - jaeger-sa

# List all roles
kubectl get roles -n ai-platform

# List all rolebindings
kubectl get rolebindings -n ai-platform
```

### Secrets

```bash
# List all secrets
kubectl get secrets -n ai-platform

# Expected output: ~10+ secrets
# - postgres-credentials
# - neo4j-credentials
# - minio-credentials
# - grafana-credentials
# - gateway-api-keys
# - mcpjungle-credentials
# - github-token
# - notion-api-key
# - kong-postgres-credentials (if Kong enabled)
# - kong-oauth2-credentials (if Kong enabled)
# - kong-jwt-keys (if Kong enabled)
# - tls-certificate (if TLS enabled)

# Verify secret encryption
ETCDCTL_API=3 etcdctl get /registry/secrets/ai-platform/postgres-credentials | hexdump -C
# Should start with 'k8s:enc:aesgcm:v1:key1:' or similar
```

## Testing Network Policies

### Test 1: Verify Default Deny

```bash
# Create a debug pod
kubectl run -it --rm debug --image=busybox --restart=Never -n ai-platform -- sh

# Inside the pod, try to connect to a service (should fail)
wget -O- --timeout=5 http://postgres:5432
# Expected: timeout or connection refused

# Exit the pod
exit
```

### Test 2: Verify Allowed Connections

```bash
# Test from gateway pod
GATEWAY_POD=$(kubectl get pods -n ai-platform -l app.kubernetes.io/name=gateway -o jsonpath='{.items[0].metadata.name}')

# Gateway should be able to reach agent-router
kubectl exec -it $GATEWAY_POD -n ai-platform -- wget -O- --timeout=5 http://agent-router:8000/health

# Gateway should be able to reach redis
kubectl exec -it $GATEWAY_POD -n ai-platform -- sh -c "echo 'PING' | nc redis 6379"
```

### Test 3: Verify DNS Access

```bash
# All pods should be able to resolve DNS
kubectl run -it --rm dns-test --image=busybox --restart=Never -n ai-platform -- nslookup kubernetes.default
# Expected: successful DNS resolution
```

## Testing RBAC

### Test 1: Verify Service Account Permissions

```bash
# Gateway should be able to get its ConfigMap
kubectl auth can-i --as=system:serviceaccount:ai-platform:gateway-sa \
  get configmaps/agent-router-config -n ai-platform
# Expected: yes

# Gateway should NOT be able to delete ConfigMaps
kubectl auth can-i --as=system:serviceaccount:ai-platform:gateway-sa \
  delete configmaps -n ai-platform
# Expected: no

# MAX Serve should NOT be able to list secrets
kubectl auth can-i --as=system:serviceaccount:ai-platform:max-serve-llama-sa \
  list secrets -n ai-platform
# Expected: no
```

### Test 2: Verify Pod Service Accounts

```bash
# Check that each pod is using its dedicated service account
kubectl get pods -n ai-platform -o custom-columns=NAME:.metadata.name,SA:.spec.serviceAccountName

# Expected: Each pod should have a unique service account
# gateway-xxx -> gateway-sa
# agent-router-xxx -> agent-router-sa
# max-serve-llama-xxx -> max-serve-llama-sa
# etc.
```

## Testing Secrets Encryption

### Test 1: Verify Encryption Configuration

```bash
# Check encryption config is loaded
kubectl get --raw /metrics | grep apiserver_storage_transformation
# Should show metrics for the encryption provider
```

### Test 2: Verify Secret Access

```bash
# Pods should still be able to read secrets normally
GATEWAY_POD=$(kubectl get pods -n ai-platform -l app.kubernetes.io/name=gateway -o jsonpath='{.items[0].metadata.name}')

kubectl exec $GATEWAY_POD -n ai-platform -- env | grep -i secret
# Should show environment variables from secrets
```

### Test 3: Direct etcd Verification (requires etcd access)

```bash
# Read encrypted data from etcd
ETCDCTL_API=3 etcdctl get /registry/secrets/ai-platform/postgres-credentials

# Should show encrypted data starting with provider name
# Example: k8s:enc:aesgcm:v1:key1:<encrypted-data>
```

## Testing Security Contexts

### Test 1: Verify Non-Root Containers

```bash
# Check that containers are running as non-root
kubectl get pods -n ai-platform -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.securityContext.runAsUser}{"\n"}{end}'

# Expected: All pods should show UID 999 or 1000 (non-root)
```

### Test 2: Verify Read-Only Filesystem

```bash
# Check container security contexts
kubectl get pod gateway-xxx -n ai-platform -o jsonpath='{.spec.containers[*].securityContext}' | jq

# Expected: readOnlyRootFilesystem: true (for most containers)
```

### Test 3: Verify Dropped Capabilities

```bash
# Check capabilities
kubectl get pod gateway-xxx -n ai-platform -o jsonpath='{.spec.containers[*].securityContext.capabilities}' | jq

# Expected: drop: ["ALL"]
```

## Common Issues and Solutions

### Issue 1: Network Policy blocks DNS

**Symptom**: Pods cannot resolve service names

**Solution**:
```bash
# Ensure DNS policy is applied
kubectl get networkpolicy allow-dns-access -n ai-platform

# If missing, ensure values.yaml has:
networkPolicies:
  allowDNS: true
```

### Issue 2: Service account permissions denied

**Symptom**: Pod logs show "forbidden: User cannot..."

**Solution**:
```bash
# Check RBAC configuration
kubectl describe rolebinding <service>-rolebinding -n ai-platform

# Verify the role has required permissions
kubectl describe role <service>-role -n ai-platform

# If missing, update values.yaml and upgrade:
helm upgrade ai-platform ./helm/ai-platform -n ai-platform
```

### Issue 3: Secrets encryption not working

**Symptom**: Secrets are stored in plain text in etcd

**Solution**:
```bash
# Verify encryption config is loaded
kubectl get --raw /metrics | grep apiserver_storage_transformation

# Re-apply encryption config to kube-apiserver
sudo vi /etc/kubernetes/manifests/kube-apiserver.yaml

# Re-encrypt secrets
kubectl get secrets --all-namespaces -o json | kubectl replace -f -
```

### Issue 4: Container security context rejected

**Symptom**: Pod fails to start with security context errors

**Solution**:
```bash
# Check pod events
kubectl describe pod <pod-name> -n ai-platform

# For PSP/PSS issues, ensure cluster supports security contexts
kubectl get psp  # Check Pod Security Policies
kubectl get ns ai-platform -o yaml  # Check namespace labels

# May need to adjust security context in values.yaml
```

## Production Deployment Checklist

- [ ] Network policies enabled and tested
- [ ] RBAC enabled with least-privilege service accounts
- [ ] Secrets encryption at rest configured
- [ ] All default passwords changed
- [ ] TLS certificates configured
- [ ] Image pull secrets configured (if using private registry)
- [ ] Security contexts applied to all pods
- [ ] Pod Security Standards/Policies configured
- [ ] Audit logging enabled
- [ ] Monitoring and alerting configured
- [ ] Backup and disaster recovery plan in place
- [ ] Security documentation reviewed
- [ ] Penetration testing completed
- [ ] Compliance requirements verified

## Monitoring Commands

```bash
# Monitor network policy metrics
kubectl get --raw /metrics | grep networkpolicy

# Monitor RBAC denials
kubectl logs -n kube-system -l component=kube-apiserver | grep "RBAC DENY"

# Monitor secret access
kubectl logs -n kube-system -l component=kube-apiserver | grep "secrets"

# Monitor security events
kubectl get events -n ai-platform --sort-by='.lastTimestamp'

# Monitor pod security
kubectl get pods -n ai-platform -o json | jq '.items[] | {name: .metadata.name, securityContext: .spec.securityContext, containers: .spec.containers[].securityContext}'
```

## Regular Maintenance

### Weekly

```bash
# Check for security events
kubectl get events -n ai-platform --sort-by='.lastTimestamp' | grep -i "security\|forbidden\|denied"

# Verify all pods are running with security contexts
kubectl get pods -n ai-platform -o json | jq '.items[] | select(.spec.securityContext.runAsUser == null)'
# Should return empty
```

### Monthly

```bash
# Review RBAC permissions
kubectl get roles,rolebindings -n ai-platform -o yaml > rbac-backup.yaml

# Review network policies
kubectl get networkpolicies -n ai-platform -o yaml > netpol-backup.yaml

# Test network isolation
# (Run the network policy tests above)
```

### Quarterly

```bash
# Rotate encryption keys
# (Follow key rotation procedure in main documentation)

# Review and update secrets
# (Rotate passwords, API keys, certificates)

# Audit RBAC permissions
# (Remove unnecessary permissions)

# Update security documentation
# (Document any changes made)
```

## Support

For detailed documentation, see [KUBERNETES_SECURITY_IMPLEMENTATION.md](./KUBERNETES_SECURITY_IMPLEMENTATION.md)

For issues:
1. Check pod logs: `kubectl logs <pod-name> -n ai-platform`
2. Check events: `kubectl get events -n ai-platform --sort-by='.lastTimestamp'`
3. Review main documentation
4. Open an issue with details
