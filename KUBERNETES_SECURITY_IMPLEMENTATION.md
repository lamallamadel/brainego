# Kubernetes Security Implementation Guide

## Overview

This document describes the complete Kubernetes security implementation for the AI Platform, including:

1. **Network Policies** - Namespace isolation with inter-pod traffic whitelisting
2. **RBAC** - Role-Based Access Control with dedicated service accounts per pod using least-privilege principle
3. **Secrets Encryption** - Kubernetes Secrets with at-rest encryption

## Table of Contents

- [Network Policies](#network-policies)
- [RBAC Configuration](#rbac-configuration)
- [Secrets Encryption](#secrets-encryption)
- [Deployment](#deployment)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)

## Network Policies

### Architecture

The network policy implementation follows a zero-trust security model:

1. **Default Deny All**: All ingress and egress traffic is denied by default
2. **DNS Access**: All pods can access kube-system DNS (required for service discovery)
3. **Explicit Allow Rules**: Each service has specific ingress/egress rules based on actual dependencies

### Network Policy Structure

```
┌─────────────────────────────────────────────────────────┐
│              ai-platform Namespace                      │
│  (Default Deny All Ingress/Egress)                     │
└─────────────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ Gateway │      │  Agent  │      │   MCP   │
    │         │─────▶│ Router  │◀─────│ Jungle  │
    └────┬────┘      └────┬────┘      └────┬────┘
         │                │                 │
         └────────┬───────┴─────┬───────────┘
                  │             │
         ┌────────▼──┐   ┌──────▼─────┐
         │ MAX Serve │   │ Databases  │
         │ Instances │   │ (Postgres, │
         │           │   │  Redis,    │
         └───────────┘   │  Qdrant)   │
                         └────────────┘
```

### Key Network Policies

#### 1. Gateway Network Policy
- **Ingress**: Accepts external traffic and traffic from Kong (if enabled)
- **Egress**: Can communicate with Agent Router, MAX Serve instances, Qdrant, and Redis

#### 2. Agent Router Network Policy
- **Ingress**: Accepts traffic from Gateway and MCPJungle
- **Egress**: Can communicate with MAX Serve, databases (Postgres, Neo4j, Qdrant, Redis)

#### 3. MAX Serve Network Policies (Llama, Qwen, DeepSeek)
- **Ingress**: Only accepts traffic from Gateway, Agent Router, and Learning Engine
- **Egress**: None (inference services don't need outbound connections)

#### 4. Database Network Policies
- **PostgreSQL**: Accepts connections from Agent Router, Learning Engine, monitoring components
- **Redis**: Accepts connections from API services, Kong
- **Qdrant**: Accepts connections from API services, Mem0
- **Neo4j**: Accepts connections from Agent Router only

#### 5. Learning Engine Network Policy
- **Ingress**: Accepts traffic from drift-monitor
- **Egress**: Can access PostgreSQL, MinIO, and MAX Serve for inference

### Enabling Network Policies

```yaml
# values.yaml
networkPolicies:
  enabled: true
  defaultDeny: true
  allowDNS: true
```

### Verifying Network Policies

```bash
# List all network policies
kubectl get networkpolicies -n ai-platform

# Describe a specific policy
kubectl describe networkpolicy gateway-network-policy -n ai-platform

# Test connectivity (should fail if not whitelisted)
kubectl run -it --rm debug --image=busybox --restart=Never -n ai-platform -- sh
# Inside the pod:
wget -O- http://postgres:5432  # Should timeout if not allowed
```

## RBAC Configuration

### Service Accounts

Each pod type has a dedicated service account with minimal required permissions:

#### API Services (Gateway, Agent Router, MCPJungle)
- **Permissions**:
  - Read ConfigMaps (for configuration)
  - Read specific Secrets (for credentials)
  - List Services and Endpoints (for service discovery)
- **automountServiceAccountToken**: true

#### Inference Services (MAX Serve instances)
- **Permissions**:
  - Read ConfigMaps (for configuration only)
- **automountServiceAccountToken**: false (minimal token usage)

#### Database Services (Postgres, Redis, Qdrant, Neo4j, MinIO)
- **Permissions**:
  - Read specific Secrets (for credentials)
  - Read ConfigMaps (for init scripts)
- **automountServiceAccountToken**: false

#### Learning Engine
- **Permissions**:
  - Read ConfigMaps (for configuration)
  - Read Secrets (Postgres, MinIO credentials)
- **automountServiceAccountToken**: true

#### Monitoring Services (Prometheus, Grafana)
- **Permissions**:
  - Prometheus: List/watch Services, Endpoints, Pods (for service discovery)
  - Grafana: Read ConfigMaps, read specific Secrets
- **automountServiceAccountToken**: true

### RBAC Resources

For each service account, the following resources are created:

1. **ServiceAccount**: Identity for the pod
2. **Role**: Defines permissions within the namespace
3. **RoleBinding**: Binds the Role to the ServiceAccount

### Example RBAC Configuration

```yaml
# Gateway Service Account
apiVersion: v1
kind: ServiceAccount
metadata:
  name: gateway-sa
  namespace: ai-platform

---
# Gateway Role (least-privilege)
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: gateway-role
  namespace: ai-platform
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["agent-router-config"]
    verbs: ["get", "watch"]
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["gateway-api-keys"]
    verbs: ["get"]

---
# Gateway RoleBinding
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: gateway-rolebinding
  namespace: ai-platform
subjects:
  - kind: ServiceAccount
    name: gateway-sa
    namespace: ai-platform
roleRef:
  kind: Role
  name: gateway-role
  apiGroup: rbac.authorization.k8s.io
```

### Enabling RBAC

```yaml
# values.yaml
rbac:
  enabled: true
  serviceAccounts:
    gateway:
      create: true
      automountServiceAccountToken: true
      annotations: {}
```

### Verifying RBAC

```bash
# List service accounts
kubectl get serviceaccounts -n ai-platform

# Check permissions for a service account
kubectl auth can-i --as=system:serviceaccount:ai-platform:gateway-sa \
  get configmaps -n ai-platform

# View role bindings
kubectl get rolebindings -n ai-platform
kubectl describe rolebinding gateway-rolebinding -n ai-platform
```

## Secrets Encryption

### Overview

Kubernetes Secrets encryption at rest protects sensitive data stored in etcd. This implementation supports multiple encryption providers:

1. **AES-GCM** (Recommended): Hardware-accelerated authenticated encryption
2. **AES-CBC**: Standard AES encryption with PKCS#7 padding
3. **KMS**: Cloud provider key management (AWS KMS, Azure Key Vault, GCP KMS)
4. **Secretbox**: NaCl encryption (XSalsa20 and Poly1305)

### Secrets Architecture

```
┌──────────────────────────────────────────────────┐
│         kube-apiserver                           │
│  ┌────────────────────────────────────┐         │
│  │  EncryptionConfiguration            │         │
│  │  - Provider: AES-GCM/KMS            │         │
│  │  - Key: [encryption key]            │         │
│  └────────────────────────────────────┘         │
└───────────────────┬──────────────────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │      etcd         │
         │  (Encrypted Data) │
         └──────────────────┘
```

### Secrets Managed

The following secrets are created and encrypted:

1. **postgres-credentials**: PostgreSQL username, password, database
2. **neo4j-credentials**: Neo4j username, password
3. **minio-credentials**: MinIO access key, secret key
4. **grafana-credentials**: Grafana admin username, password
5. **gateway-api-keys**: API keys for Gateway service
6. **mcpjungle-credentials**: API keys for MCPJungle
7. **github-token**: GitHub personal access token
8. **notion-api-key**: Notion API key
9. **redis-credentials**: Redis password (optional)
10. **qdrant-credentials**: Qdrant API key (optional)
11. **kong-postgres-credentials**: Kong database credentials
12. **kong-oauth2-credentials**: Kong OAuth2 configuration
13. **kong-jwt-keys**: Kong JWT signing keys
14. **tls-certificate**: TLS certificates for HTTPS
15. **encryption-keys**: Application-level encryption keys

### Setup Encryption at Rest

#### Step 1: Generate Encryption Key

```bash
# For AES-GCM or AES-CBC
head -c 32 /dev/urandom | base64
```

#### Step 2: Configure Encryption Provider

Update `values.yaml`:

```yaml
secrets:
  encryption:
    enabled: true
    provider: aesgcm  # or: aescbc, kms, secretbox
    aesgcm:
      key: "<base64-encoded-key>"
```

#### Step 3: Apply EncryptionConfiguration

The Helm chart creates a ConfigMap with the encryption configuration. Apply it to the master node(s):

```bash
# Extract encryption config from ConfigMap
kubectl get configmap secrets-encryption-config -n ai-platform \
  -o jsonpath='{.data.encryption-config\.yaml}' > /tmp/encryption-config.yaml

# Copy to master node(s)
sudo mkdir -p /etc/kubernetes/enc
sudo cp /tmp/encryption-config.yaml /etc/kubernetes/enc/
sudo chmod 600 /etc/kubernetes/enc/encryption-config.yaml
sudo chown root:root /etc/kubernetes/enc/encryption-config.yaml
```

#### Step 4: Update kube-apiserver Configuration

For kubeadm clusters, edit `/etc/kubernetes/manifests/kube-apiserver.yaml`:

```yaml
spec:
  containers:
  - command:
    - kube-apiserver
    - --encryption-provider-config=/etc/kubernetes/enc/encryption-config.yaml
    # ... other flags
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

For managed Kubernetes (EKS, AKS, GKE), follow cloud provider documentation.

#### Step 5: Restart kube-apiserver

```bash
# For kubeadm (automatic restart)
# Wait for kube-apiserver pod to restart
kubectl get pods -n kube-system | grep kube-apiserver

# Verify health
kubectl get --raw /healthz/etcd
```

#### Step 6: Re-encrypt Existing Secrets

```bash
# Re-encrypt all secrets
kubectl get secrets --all-namespaces -o json | kubectl replace -f -

# Verify encryption
ETCDCTL_API=3 etcdctl get /registry/secrets/ai-platform/postgres-credentials | hexdump -C
# Should start with 'k8s:enc:aesgcm:v1:key1:' or similar
```

### KMS Provider Setup (Cloud Environments)

#### AWS KMS

```yaml
secrets:
  encryption:
    enabled: true
    provider: kms
    kms:
      name: aws-kms
      endpoint: unix:///var/run/kmsplugin/socket.sock
      cacheSize: 1000
      timeout: 3s
```

Install AWS KMS plugin on master nodes:
```bash
# Download AWS KMS plugin
wget https://github.com/kubernetes-sigs/aws-encryption-provider/releases/download/v0.4.0/aws-encryption-provider

# Install and configure
sudo cp aws-encryption-provider /usr/local/bin/
sudo chmod +x /usr/local/bin/aws-encryption-provider

# Create systemd service
sudo systemctl enable aws-encryption-provider
sudo systemctl start aws-encryption-provider
```

#### Azure Key Vault

```yaml
secrets:
  encryption:
    enabled: true
    provider: kms
    kms:
      name: azure-kv
      endpoint: unix:///var/run/kmsplugin/socket.sock
```

#### GCP Cloud KMS

```yaml
secrets:
  encryption:
    enabled: true
    provider: kms
    kms:
      name: gcp-kms
      endpoint: unix:///var/run/kmsplugin/socket.sock
```

### Key Rotation

#### Step 1: Generate New Key

```bash
NEW_KEY=$(head -c 32 /dev/urandom | base64)
echo $NEW_KEY
```

#### Step 2: Update encryption-config.yaml

Add new key as first entry:

```yaml
resources:
  - resources:
      - secrets
    providers:
      - aesgcm:
          keys:
            - name: key2
              secret: <new-key>
            - name: key1
              secret: <old-key>
      - identity: {}
```

#### Step 3: Update kube-apiserver

Copy updated configuration and restart kube-apiserver.

#### Step 4: Re-encrypt Secrets

```bash
kubectl get secrets --all-namespaces -o json | kubectl replace -f -
```

#### Step 5: Remove Old Key

After verifying all secrets are re-encrypted with new key, remove old key from configuration.

### Monitoring Encryption

```bash
# Check encryption provider metrics
kubectl get --raw /metrics | grep apiserver_storage_transformation

# View secret encryption status
kubectl get secret postgres-credentials -n ai-platform -o yaml
```

## Deployment

### Prerequisites

- Kubernetes cluster 1.21+ (for network policy support)
- kubectl configured with cluster admin access
- Helm 3.x installed

### Installation

```bash
# Add repository (if applicable)
# helm repo add ai-platform https://charts.example.com

# Install with default values
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace

# Install with custom values
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace \
  --values custom-values.yaml

# Install with secrets encryption
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace \
  --set secrets.encryption.enabled=true \
  --set secrets.encryption.provider=aesgcm \
  --set secrets.encryption.aesgcm.key="$(head -c 32 /dev/urandom | base64)"
```

### Upgrading

```bash
# Upgrade to latest version
helm upgrade ai-platform ./helm/ai-platform \
  --namespace ai-platform

# Upgrade with new values
helm upgrade ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --values updated-values.yaml
```

### Verification

```bash
# Check all resources
kubectl get all -n ai-platform

# Check network policies
kubectl get networkpolicies -n ai-platform

# Check service accounts
kubectl get serviceaccounts -n ai-platform

# Check secrets
kubectl get secrets -n ai-platform

# Check RBAC
kubectl get roles,rolebindings -n ai-platform

# Test pod security
kubectl get pods -n ai-platform -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.serviceAccountName}{"\n"}{end}'
```

## Security Best Practices

### 1. Network Security

- **Enable Network Policies**: Always enable network policies in production
- **Regular Audits**: Review network policies quarterly for unnecessary permissions
- **Monitoring**: Monitor denied connections to detect potential issues
- **Testing**: Test network policies in staging before production deployment

### 2. RBAC Security

- **Least Privilege**: Grant minimum permissions required for each service
- **Service Account Isolation**: Use dedicated service accounts per service
- **Regular Reviews**: Audit RBAC permissions quarterly
- **Avoid Wildcards**: Don't use wildcards (*) in resource names
- **Disable AutoMount**: Set `automountServiceAccountToken: false` when not needed

### 3. Secrets Management

- **Encryption at Rest**: Always enable secrets encryption in production
- **Key Rotation**: Rotate encryption keys quarterly
- **Immutable Secrets**: Use `immutable: true` for secrets that shouldn't change
- **External Secrets**: Consider using External Secrets Operator for production
- **Backup Keys**: Store encryption keys securely offline
- **KMS Provider**: Use cloud KMS providers in production for better security

### 4. Container Security

- **Non-Root**: Run all containers as non-root users
- **Read-Only Filesystem**: Use read-only root filesystem where possible
- **Drop Capabilities**: Drop all Linux capabilities and add back only required ones
- **Security Context**: Always define pod and container security contexts
- **Image Scanning**: Scan container images for vulnerabilities

### 5. Monitoring and Auditing

- **Audit Logging**: Enable Kubernetes audit logging
- **Network Monitoring**: Monitor network traffic for anomalies
- **Secret Access**: Audit secret access patterns
- **RBAC Monitoring**: Track RBAC permission usage
- **Alerts**: Set up alerts for security events

### 6. Compliance

- **Documentation**: Document all security configurations
- **Change Management**: Track all security-related changes
- **Compliance Reports**: Generate regular compliance reports
- **Penetration Testing**: Conduct regular security assessments

## Troubleshooting

### Network Policy Issues

#### Problem: Pod cannot connect to service

```bash
# Check network policies
kubectl get networkpolicies -n ai-platform

# Describe the policy
kubectl describe networkpolicy <policy-name> -n ai-platform

# Check pod labels
kubectl get pods -n ai-platform --show-labels

# Test connectivity
kubectl run -it --rm debug --image=busybox --restart=Never -n ai-platform -- sh
# Inside pod:
wget -O- http://service-name:port
```

#### Problem: DNS not working

Ensure DNS access is allowed:
```yaml
networkPolicies:
  allowDNS: true
```

### RBAC Issues

#### Problem: Pod cannot access ConfigMap/Secret

```bash
# Check service account
kubectl get pod <pod-name> -n ai-platform -o jsonpath='{.spec.serviceAccountName}'

# Check permissions
kubectl auth can-i --as=system:serviceaccount:ai-platform:<sa-name> \
  get configmaps -n ai-platform

# View role details
kubectl describe role <role-name> -n ai-platform
kubectl describe rolebinding <rolebinding-name> -n ai-platform
```

#### Problem: Service account token not mounted

Check deployment configuration:
```yaml
rbac:
  serviceAccounts:
    <service>:
      automountServiceAccountToken: true
```

### Secrets Encryption Issues

#### Problem: kube-apiserver fails to start

```bash
# Check kube-apiserver logs
kubectl logs -n kube-system <kube-apiserver-pod>

# Verify encryption config syntax
kubectl get configmap secrets-encryption-config -n ai-platform \
  -o jsonpath='{.data.encryption-config\.yaml}' | yamllint -

# Check file permissions
sudo ls -la /etc/kubernetes/enc/encryption-config.yaml
# Should be: -rw------- 1 root root
```

#### Problem: Secrets cannot be read

```bash
# Check if encryption is working
kubectl get secret postgres-credentials -n ai-platform -o yaml

# Verify encryption provider is configured
kubectl get --raw /metrics | grep apiserver_storage_transformation

# Check etcd data (requires etcd access)
ETCDCTL_API=3 etcdctl get /registry/secrets/ai-platform/postgres-credentials
```

#### Problem: Performance degradation

```bash
# Monitor encryption metrics
kubectl get --raw /metrics | grep apiserver_storage_transformation_duration

# For KMS provider, increase cache size
# In values.yaml:
secrets:
  encryption:
    kms:
      cacheSize: 5000  # Increase from default 1000
```

### General Security Issues

#### Problem: Security context constraints

```bash
# Check pod security context
kubectl get pod <pod-name> -n ai-platform -o jsonpath='{.spec.securityContext}'

# Check container security context
kubectl get pod <pod-name> -n ai-platform -o jsonpath='{.spec.containers[0].securityContext}'
```

#### Problem: Image pull errors with private registries

```bash
# Check image pull secrets
kubectl get secrets -n ai-platform | grep docker

# Create image pull secret
kubectl create secret docker-registry regcred \
  --docker-server=<registry> \
  --docker-username=<username> \
  --docker-password=<password> \
  -n ai-platform

# Update values.yaml
imagePullSecrets:
  - name: regcred
```

## References

- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Encrypting Secret Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/)
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Security Best Practices](https://kubernetes.io/docs/concepts/security/security-best-practices/)

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Kubernetes and Helm logs
3. Consult the official Kubernetes documentation
4. Open an issue in the project repository
