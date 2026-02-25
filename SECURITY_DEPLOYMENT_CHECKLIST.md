# Security Deployment Checklist

Use this checklist to ensure all security features are properly configured before deploying to production.

## Pre-Deployment Checklist

### 1. Secrets Management

- [ ] Generate strong encryption keys
  ```bash
  # AES-GCM encryption key
  head -c 32 /dev/urandom | base64
  ```

- [ ] Replace all default passwords
  - [ ] PostgreSQL password
  - [ ] Neo4j password
  - [ ] MinIO access key and secret key
  - [ ] Grafana admin password
  - [ ] Redis password (if enabled)
  - [ ] Qdrant API key (if enabled)
  - [ ] Kong database password

- [ ] Generate API keys
  - [ ] Gateway API keys
  - [ ] MCPJungle API keys

- [ ] Configure external service credentials
  - [ ] GitHub personal access token
  - [ ] Notion API key
  - [ ] Slack webhook URL (if using)

- [ ] Generate TLS certificates
  - [ ] TLS certificate
  - [ ] TLS private key
  - [ ] CA certificate (if applicable)

- [ ] Generate Kong JWT keys
  ```bash
  # Generate RSA key pair
  openssl genrsa -out private.key 2048
  openssl rsa -in private.key -pubout -out public.key
  # Base64 encode for values.yaml
  cat private.key | base64 -w 0
  cat public.key | base64 -w 0
  ```

### 2. Network Policies

- [ ] Enable network policies
  ```yaml
  networkPolicies:
    enabled: true
    defaultDeny: true
    allowDNS: true
  ```

- [ ] Verify CNI plugin supports network policies
  - [ ] Calico
  - [ ] Cilium
  - [ ] Weave Net
  - [ ] Canal
  - [ ] Or other compatible CNI

- [ ] Review network policy rules
  - [ ] Default deny all ingress/egress
  - [ ] DNS access allowed
  - [ ] Service-to-service communication rules
  - [ ] External access rules (if needed)

### 3. RBAC Configuration

- [ ] Enable RBAC
  ```yaml
  rbac:
    enabled: true
  ```

- [ ] Configure service accounts
  - [ ] Gateway service account
  - [ ] Agent Router service account
  - [ ] MCPJungle service account
  - [ ] MAX Serve service accounts (3x)
  - [ ] Learning Engine service account
  - [ ] Mem0 service account
  - [ ] Database service accounts (5x)
  - [ ] Monitoring service accounts (3x)

- [ ] Review service account permissions
  - [ ] Each service has minimal required permissions
  - [ ] No wildcard resource names
  - [ ] No cluster-wide permissions

- [ ] Configure cloud provider IAM (if applicable)
  - [ ] AWS IAM roles for service accounts (IRSA)
  - [ ] GCP Workload Identity
  - [ ] Azure Managed Identity

### 4. Secrets Encryption at Rest

- [ ] Choose encryption provider
  - [ ] AES-GCM (recommended for most use cases)
  - [ ] AES-CBC (alternative)
  - [ ] KMS (for cloud deployments)
  - [ ] Secretbox (NaCl)

- [ ] Generate encryption key
  ```bash
  head -c 32 /dev/urandom | base64
  ```

- [ ] Configure encryption in values.yaml
  ```yaml
  secrets:
    encryption:
      enabled: true
      provider: aesgcm
      aesgcm:
        key: "<generated-key>"
  ```

- [ ] Apply encryption configuration to master nodes
  - [ ] Copy encryption-config.yaml to /etc/kubernetes/enc/
  - [ ] Set permissions (600, root:root)
  - [ ] Update kube-apiserver manifest
  - [ ] Restart kube-apiserver
  - [ ] Re-encrypt existing secrets

- [ ] For KMS provider (cloud environments)
  - [ ] Install KMS plugin on master nodes
  - [ ] Configure KMS endpoint
  - [ ] Verify KMS connectivity
  - [ ] Test encryption/decryption

### 5. Pod Security

- [ ] Configure pod security contexts
  ```yaml
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  ```

- [ ] Configure container security contexts
  ```yaml
  containerSecurityContext:
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    runAsNonRoot: true
    runAsUser: 1000
    capabilities:
      drop:
        - ALL
  ```

- [ ] Configure Pod Security Standards/Admission
  - [ ] Baseline policy for namespace
  - [ ] Restricted policy for sensitive workloads
  - [ ] PSP or PSA configured

### 6. TLS/SSL Configuration

- [ ] Enable TLS
  ```yaml
  tls:
    enabled: true
  ```

- [ ] Configure certificates
  - [ ] Upload TLS certificate
  - [ ] Upload private key
  - [ ] Upload CA certificate (if applicable)

- [ ] Configure cert-manager (for automatic renewal)
  - [ ] Install cert-manager
  - [ ] Configure Let's Encrypt or other ACME provider
  - [ ] Create Certificate resources

### 7. Ingress and Load Balancer

- [ ] Configure Kong ingress (if enabled)
  - [ ] OAuth2 configuration
  - [ ] JWT configuration
  - [ ] Rate limiting
  - [ ] Token budget
  - [ ] Audit logging

- [ ] Configure ingress rules
  - [ ] Domain names
  - [ ] TLS termination
  - [ ] Path routing
  - [ ] Authentication

- [ ] Configure load balancer
  - [ ] Type (LoadBalancer, NodePort, ClusterIP)
  - [ ] External IP/hostname
  - [ ] Health checks

### 8. Monitoring and Logging

- [ ] Configure Prometheus
  - [ ] Service discovery
  - [ ] Scrape configs
  - [ ] Retention period
  - [ ] Alert rules

- [ ] Configure Grafana
  - [ ] Data sources
  - [ ] Dashboards
  - [ ] Alert notifications

- [ ] Configure audit logging
  - [ ] kube-apiserver audit policy
  - [ ] Audit log retention
  - [ ] Log aggregation

- [ ] Configure security monitoring
  - [ ] Network policy violations
  - [ ] RBAC denials
  - [ ] Secret access patterns
  - [ ] Security events

### 9. High Availability

- [ ] Configure replica counts
  - [ ] API services: 2-3 replicas
  - [ ] Inference services: 2+ replicas
  - [ ] Databases: Consider external HA solutions

- [ ] Configure pod disruption budgets
  - [ ] minAvailable or maxUnavailable set
  - [ ] Appropriate for each service

- [ ] Configure affinity/anti-affinity
  - [ ] Pod anti-affinity for API services
  - [ ] Node affinity for GPU workloads

- [ ] Configure autoscaling
  - [ ] HPA for stateless services
  - [ ] Custom metrics (if applicable)
  - [ ] Scale-up/down policies

### 10. Backup and Disaster Recovery

- [ ] Backup encryption keys
  - [ ] Store securely offline
  - [ ] Document key location
  - [ ] Test key recovery

- [ ] Backup secrets
  - [ ] Export encrypted secrets
  - [ ] Store in secure location
  - [ ] Test secret restore

- [ ] Backup persistent data
  - [ ] PostgreSQL database
  - [ ] Redis data
  - [ ] Qdrant collections
  - [ ] Neo4j graph data
  - [ ] MinIO objects

- [ ] Document recovery procedures
  - [ ] Cluster recovery
  - [ ] Data restoration
  - [ ] Secret rotation

## Deployment

### 1. Install Helm Chart

```bash
# Review values file
cat helm/ai-platform/values-production-secure.yaml

# Install with production values
helm install ai-platform ./helm/ai-platform \
  --namespace ai-platform \
  --create-namespace \
  --values helm/ai-platform/values-production-secure.yaml
```

### 2. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n ai-platform

# Check all services
kubectl get services -n ai-platform

# Check network policies
kubectl get networkpolicies -n ai-platform

# Check service accounts
kubectl get serviceaccounts -n ai-platform

# Check secrets
kubectl get secrets -n ai-platform
```

### 3. Test Security Features

```bash
# Test network policies
./test-network-policies.sh

# Test RBAC
./test-rbac.sh

# Test secrets encryption
./test-secrets-encryption.sh
```

## Post-Deployment Checklist

### 1. Security Verification

- [ ] Network policies are enforced
  - [ ] Test default deny
  - [ ] Test allowed connections
  - [ ] Test DNS access

- [ ] RBAC is working
  - [ ] Service accounts assigned
  - [ ] Permissions verified
  - [ ] No unauthorized access

- [ ] Secrets are encrypted
  - [ ] Encryption verified in etcd
  - [ ] Secrets accessible by pods
  - [ ] No plaintext secrets

- [ ] Pod security is enforced
  - [ ] Non-root containers
  - [ ] Read-only filesystems
  - [ ] Dropped capabilities

- [ ] TLS is working
  - [ ] HTTPS endpoints accessible
  - [ ] Valid certificates
  - [ ] Proper cipher suites

### 2. Functional Testing

- [ ] API endpoints responding
  - [ ] Gateway service
  - [ ] Agent Router service
  - [ ] MCPJungle service

- [ ] Inference services working
  - [ ] Llama model
  - [ ] Qwen model
  - [ ] DeepSeek model

- [ ] Database connectivity
  - [ ] PostgreSQL
  - [ ] Redis
  - [ ] Qdrant
  - [ ] Neo4j
  - [ ] MinIO

- [ ] Monitoring working
  - [ ] Prometheus scraping
  - [ ] Grafana dashboards
  - [ ] Alerts configured

### 3. Performance Testing

- [ ] Load testing completed
- [ ] Latency within acceptable range
- [ ] Resource usage monitored
- [ ] Autoscaling working

### 4. Documentation

- [ ] Deployment documented
- [ ] Security configuration documented
- [ ] Runbooks created
- [ ] Incident response plan documented
- [ ] Backup/restore procedures documented

### 5. Training

- [ ] Operations team trained
- [ ] Security team briefed
- [ ] Runbooks reviewed
- [ ] Incident response drills conducted

## Ongoing Maintenance

### Daily

- [ ] Check cluster health
- [ ] Review security events
- [ ] Monitor resource usage

### Weekly

- [ ] Review audit logs
- [ ] Check for security updates
- [ ] Verify backup integrity

### Monthly

- [ ] Review RBAC permissions
- [ ] Review network policies
- [ ] Update security documentation
- [ ] Security metrics review

### Quarterly

- [ ] Rotate encryption keys
- [ ] Rotate credentials
- [ ] Security audit
- [ ] Penetration testing
- [ ] Disaster recovery drill

### Annually

- [ ] Comprehensive security review
- [ ] Update security policies
- [ ] Compliance audit
- [ ] Architecture review

## Compliance Checklist

### CIS Kubernetes Benchmark

- [ ] 1.2.1 - Ensure that the --anonymous-auth argument is set to false
- [ ] 1.2.2 - Ensure that the --basic-auth-file argument is not set
- [ ] 3.2.1 - Ensure that a minimal audit policy is created
- [ ] 4.1.1 - Ensure that the kubelet service file permissions are set to 644
- [ ] 5.1.1 - Ensure that the cluster-admin role is only used where required
- [ ] 5.1.5 - Ensure that default service accounts are not actively used
- [ ] 5.2.2 - Minimize the admission of containers wishing to share the host process ID namespace
- [ ] 5.3.2 - Ensure that all Namespaces have Network Policies defined
- [ ] 5.7.1 - Create administrative boundaries between resources using namespaces
- [ ] 5.7.2 - Ensure that the seccomp profile is set to docker/default in your pod definitions
- [ ] 5.7.3 - Apply Security Context to Your Pods and Containers
- [ ] 5.7.4 - The default namespace should not be used

### PCI DSS

- [ ] Requirement 1 - Network security controls implemented
- [ ] Requirement 2 - Secure configuration maintained
- [ ] Requirement 3 - Data encryption in place
- [ ] Requirement 7 - Access control implemented
- [ ] Requirement 8 - Authentication mechanisms
- [ ] Requirement 10 - Audit logging enabled

### HIPAA

- [ ] Access Control (§164.312(a)(1))
- [ ] Audit Controls (§164.312(b))
- [ ] Integrity (§164.312(c)(1))
- [ ] Transmission Security (§164.312(e)(1))
- [ ] Encryption (§164.312(a)(2)(iv))

### SOC 2

- [ ] Security principle
- [ ] Availability principle
- [ ] Processing integrity
- [ ] Confidentiality
- [ ] Privacy

## Emergency Contacts

- **Security Team**: security@example.com
- **Operations Team**: ops@example.com
- **On-Call**: oncall@example.com
- **Emergency**: +1-XXX-XXX-XXXX

## References

- [KUBERNETES_SECURITY_IMPLEMENTATION.md](./KUBERNETES_SECURITY_IMPLEMENTATION.md)
- [SECURITY_QUICKSTART.md](./SECURITY_QUICKSTART.md)
- [SECURITY_FEATURES.md](./SECURITY_FEATURES.md)
- [values-production-secure.yaml](./helm/ai-platform/values-production-secure.yaml)

## Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Security Lead | | | |
| Operations Lead | | | |
| Project Manager | | | |
| CTO/CISO | | | |

---

**Last Updated**: 2024-01-01  
**Next Review**: 2024-04-01  
**Document Owner**: Security Team
