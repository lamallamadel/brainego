# Kong Ingress Controller Deployment Guide

## Overview

This guide covers deploying Kong Ingress Controller with:
- **OAuth 2.1** with PKCE (Proof Key for Code Exchange)
- **JWT Authentication** using RS256 tokens
- **Multi-layer Rate Limiting**:
  - 100 requests/minute per IP
  - 1000 requests/hour per user
  - Daily token budget per workspace
- **TLS 1.3** via cert-manager + Let's Encrypt
- **Structured Audit Logging** (user, tokens, latency, model, tools)

## Architecture

```
                    ┌─────────────────────────────────┐
                    │     Let's Encrypt (TLS 1.3)     │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │    Kong Ingress Controller      │
                    │  - OAuth 2.1 (PKCE)             │
                    │  - JWT (RS256)                  │
                    │  - Rate Limiting (3 layers)     │
                    │  - Audit Logging                │
                    └──────────────┬──────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│ Agent Router  │        │   Gateway     │        │  MCPJungle    │
│   (8000)      │        │   (9002)      │        │   (9100)      │
└───────────────┘        └───────────────┘        └───────────────┘
```

## Prerequisites

1. **Kubernetes Cluster** (1.24+)
2. **Helm 3** (3.10+)
3. **kubectl** configured
4. **Domain name** with DNS configured
5. **Redis** for rate limiting (deployed by chart)
6. **PostgreSQL** for Kong database (deployed by chart)

## Quick Start

### 1. Add Helm Repositories

```bash
helm repo add kong https://charts.konghq.com
helm repo add jetstack https://charts.jetstack.io
helm repo update
```

### 2. Generate JWT Key Pair (RS256)

```bash
# Generate private key
openssl genrsa -out kong-jwt-private.pem 4096

# Generate public key
openssl rsa -in kong-jwt-private.pem -pubout -out kong-jwt-public.pem

# Base64 encode for Kubernetes secrets
PRIVATE_KEY_B64=$(base64 -w 0 kong-jwt-private.pem)
PUBLIC_KEY_B64=$(base64 -w 0 kong-jwt-public.pem)

echo "Private Key (Base64): $PRIVATE_KEY_B64"
echo "Public Key (Base64): $PUBLIC_KEY_B64"
```

### 3. Update Configuration

Edit `helm/ai-platform/values.yaml`:

```yaml
kong:
  enabled: true
  
  jwt:
    privateKey: <PRIVATE_KEY_B64>
    publicKey: <PUBLIC_KEY_B64>
  
  oauth2:
    adminClientId: <generate-random-uuid>
    adminClientSecret: <generate-random-secret>
    provisionKey: <generate-random-provision-key>
    redirectUri: https://your-domain.com/auth/callback
  
  ingress:
    host: api.your-domain.com

certManager:
  enabled: true
  email: admin@your-domain.com
```

### 4. Deploy

```bash
# Install dependencies (Kong and cert-manager)
cd helm/ai-platform
helm dependency update

# Install the chart
helm install ai-platform . \
  --namespace ai-platform \
  --create-namespace \
  --wait \
  --timeout 10m
```

### 5. Verify Deployment

```bash
# Check Kong pods
kubectl get pods -n ai-platform -l app.kubernetes.io/name=kong

# Check Ingress Controller
kubectl get pods -n ai-platform -l app=ingress-kong

# Check cert-manager
kubectl get pods -n cert-manager

# Check certificates
kubectl get certificates -n ai-platform

# Check ingress
kubectl get ingress -n ai-platform
```

## Authentication Flow

### OAuth 2.1 Authorization Code Flow with PKCE

1. **Client Registration**:
   ```bash
   # Get OAuth2 provider endpoint
   KONG_ADMIN_URL=$(kubectl get svc -n ai-platform kong-admin -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
   
   # Register application
   curl -X POST http://$KONG_ADMIN_URL:8001/consumers/admin/oauth2 \
     -d "name=My Application" \
     -d "client_id=your-client-id" \
     -d "client_secret=your-client-secret" \
     -d "redirect_uris[]=https://your-app.com/callback"
   ```

2. **Authorization Request** (with PKCE):
   ```
   GET https://api.your-domain.com/oauth2/authorize?
     response_type=code&
     client_id=your-client-id&
     redirect_uri=https://your-app.com/callback&
     scope=api.read api.write&
     code_challenge=<SHA256(code_verifier)>&
     code_challenge_method=S256
   ```

3. **Token Exchange**:
   ```bash
   curl -X POST https://api.your-domain.com/oauth2/token \
     -d "grant_type=authorization_code" \
     -d "client_id=your-client-id" \
     -d "client_secret=your-client-secret" \
     -d "code=<authorization_code>" \
     -d "code_verifier=<original_verifier>"
   ```

4. **Use Access Token**:
   ```bash
   curl -H "Authorization: Bearer <access_token>" \
     https://api.your-domain.com/v1/chat/completions
   ```

### JWT Authentication (RS256)

1. **Generate JWT**:
   ```python
   import jwt
   import datetime
   
   # Load private key
   with open('kong-jwt-private.pem', 'r') as f:
       private_key = f.read()
   
   # Create JWT payload
   payload = {
       'iss': 'admin-key',  # Key claim name
       'sub': 'user-id',
       'aud': 'ai-platform',
       'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
       'nbf': datetime.datetime.utcnow(),
       'iat': datetime.datetime.utcnow(),
       'kid': 'admin-key',
       'scopes': ['api.read', 'api.write']
   }
   
   # Sign JWT with RS256
   token = jwt.encode(payload, private_key, algorithm='RS256')
   print(f"JWT Token: {token}")
   ```

2. **Use JWT**:
   ```bash
   curl -H "Authorization: Bearer <jwt_token>" \
     https://api.your-domain.com/v1/chat/completions \
     -d '{"messages": [{"role": "user", "content": "Hello"}]}'
   ```

## Rate Limiting

### Layer 1: IP-based (100/minute)

```bash
# Test IP rate limit
for i in {1..105}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    https://api.your-domain.com/v1/chat/completions \
    -H "Authorization: Bearer $TOKEN"
done
# First 100 requests: 200 OK
# Requests 101-105: 429 Too Many Requests
```

### Layer 2: User-based (1000/hour)

```bash
# Check rate limit headers
curl -I -H "Authorization: Bearer $TOKEN" \
  https://api.your-domain.com/v1/chat/completions

# Response headers:
# X-RateLimit-Limit-Hour: 1000
# X-RateLimit-Remaining-Hour: 999
# X-RateLimit-Reset: 1234567890
```

### Layer 3: Workspace Token Budget (Daily)

```bash
# Check token budget
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Workspace-Id: workspace-123" \
     https://api.your-domain.com/v1/chat/completions \
     -d '{"messages": [{"role": "user", "content": "Hello"}]}'

# Response headers:
# X-Token-Budget-Limit: 1000000
# X-Token-Budget-Used: 50
# X-Token-Budget-Remaining: 999950
```

## Audit Logging

### Log Format

Structured JSON logs include:

```json
{
  "timestamp": "2024-01-15T12:34:56Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-123",
  "workspace_id": "workspace-456",
  "method": "POST",
  "path": "/v1/chat/completions",
  "status_code": 200,
  "latency_ms": 245,
  "tokens_used": 150,
  "model_name": "llama-3.3-8b-instruct",
  "tools_used": ["search", "calculator"],
  "ip_address": "192.168.1.100",
  "user_agent": "curl/7.68.0"
}
```

### Access Logs

```bash
# View file logs
kubectl exec -n ai-platform -it <kong-pod> -- tail -f /var/log/kong/audit.log

# Query structured logs
kubectl logs -n ai-platform -l app.kubernetes.io/name=kong \
  | jq 'select(.tokens_used > 1000)'
```

### Prometheus Metrics

```promql
# Request rate by status code
rate(kong_http_requests_total[5m])

# Latency percentiles
histogram_quantile(0.95, rate(kong_request_latency_ms_bucket[5m]))

# Token usage by workspace
sum by (workspace_id) (kong_tokens_used_total)

# Rate limit hits
rate(kong_rate_limiting_exceeded_total[5m])
```

## TLS 1.3 Configuration

### Verify TLS Configuration

```bash
# Check TLS version and ciphers
openssl s_client -connect api.your-domain.com:443 -tls1_3

# Expected output:
# Protocol  : TLSv1.3
# Cipher    : TLS_AES_256_GCM_SHA384
```

### Certificate Auto-renewal

cert-manager automatically renews certificates 30 days before expiration.

```bash
# Check certificate status
kubectl describe certificate ai-platform-tls -n ai-platform

# Force renewal (testing)
kubectl delete secret ai-platform-tls -n ai-platform
# cert-manager will automatically recreate
```

## Monitoring

### Kong Prometheus Metrics

```bash
# Access Prometheus metrics
kubectl port-forward -n ai-platform svc/kong-proxy 8100:8100
curl http://localhost:8100/metrics
```

Key metrics:
- `kong_http_requests_total` - Total HTTP requests
- `kong_request_latency_ms` - Request latency histogram
- `kong_bandwidth_bytes` - Bandwidth usage
- `kong_datastore_reachable` - Database connectivity
- `kong_nginx_connections_total` - Active connections

### Grafana Dashboards

Import Kong dashboards:

```bash
# Access Grafana
kubectl port-forward -n ai-platform svc/grafana 3000:3000

# Navigate to: http://localhost:3000
# Import dashboard ID: 7424 (Kong Official Dashboard)
```

## Troubleshooting

### OAuth2 Issues

```bash
# Check OAuth2 plugin configuration
kubectl exec -n ai-platform <kong-pod> -- \
  kong config db_export

# Verify consumer credentials
KONG_ADMIN=$(kubectl get svc -n ai-platform kong-admin -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl http://$KONG_ADMIN:8001/consumers/admin/oauth2
```

### JWT Validation Errors

```bash
# Check JWT plugin logs
kubectl logs -n ai-platform -l app.kubernetes.io/name=kong | grep jwt

# Common issues:
# - Public key mismatch
# - Expired token (exp claim)
# - Invalid signature
# - Missing kid claim
```

### Rate Limit Issues

```bash
# Check Redis connectivity
kubectl exec -n ai-platform <kong-pod> -- \
  redis-cli -h redis -p 6379 ping

# View rate limit keys
kubectl exec -n ai-platform -it redis-0 -- \
  redis-cli --scan --pattern "ratelimit:*"

# Check rate limit values
kubectl exec -n ai-platform -it redis-0 -- \
  redis-cli get "ratelimit:192.168.1.100:v1/chat/completions:minute"
```

### TLS Certificate Issues

```bash
# Check certificate status
kubectl describe certificate -n ai-platform

# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager

# Check challenge status
kubectl describe challenge -n ai-platform

# Manual certificate renewal
kubectl delete certificate ai-platform-tls -n ai-platform
kubectl apply -f helm/ai-platform/templates/cert-manager-issuer.yaml
```

## Security Best Practices

1. **Rotate Secrets Regularly**:
   ```bash
   # Generate new OAuth2 client secret
   NEW_SECRET=$(openssl rand -base64 32)
   kubectl create secret generic kong-oauth2-credentials \
     --from-literal=adminClientSecret=$NEW_SECRET \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

2. **Use Strong JWT Keys**:
   - Minimum 4096-bit RSA keys
   - Rotate keys every 90 days
   - Store private keys in sealed secrets or external vault

3. **Monitor Anomalies**:
   - Set up alerts for rate limit violations
   - Monitor failed authentication attempts
   - Track unusual token usage patterns

4. **Network Policies**:
   ```yaml
   apiVersion: networking.k8s.io/v1
   kind: NetworkPolicy
   metadata:
     name: kong-network-policy
   spec:
     podSelector:
       matchLabels:
         app: kong
     ingress:
     - from:
       - podSelector: {}
       ports:
       - protocol: TCP
         port: 8000
       - protocol: TCP
         port: 8443
   ```

## Performance Tuning

### Kong Configuration

```yaml
kong:
  env:
    nginx_worker_processes: auto
    nginx_worker_connections: 10000
    mem_cache_size: 256m
    upstream_keepalive_max_requests: 1000
    upstream_keepalive_idle_timeout: 60
```

### Redis Optimization

```yaml
redis:
  args:
    - redis-server
    - --maxmemory
    - 4gb
    - --maxmemory-policy
    - allkeys-lru
    - --tcp-backlog
    - 511
```

### Database Connection Pooling

```yaml
kong:
  env:
    pg_max_concurrent_queries: 0
    pg_semaphore_timeout: 60000
```

## Backup and Recovery

### Backup Kong Configuration

```bash
# Export Kong configuration
kubectl exec -n ai-platform <kong-pod> -- \
  kong config db_export /tmp/kong-backup.yaml

# Copy backup locally
kubectl cp ai-platform/<kong-pod>:/tmp/kong-backup.yaml ./kong-backup.yaml
```

### Restore Configuration

```bash
# Copy backup to pod
kubectl cp ./kong-backup.yaml ai-platform/<kong-pod>:/tmp/kong-backup.yaml

# Import configuration
kubectl exec -n ai-platform <kong-pod> -- \
  kong config db_import /tmp/kong-backup.yaml
```

## Production Checklist

- [ ] Update all default credentials
- [ ] Configure production domain names
- [ ] Generate production JWT key pairs
- [ ] Set up monitoring and alerting
- [ ] Configure backup automation
- [ ] Enable audit log shipping
- [ ] Set up log aggregation
- [ ] Configure network policies
- [ ] Enable pod security policies
- [ ] Set resource limits and requests
- [ ] Configure horizontal pod autoscaling
- [ ] Test disaster recovery procedures
- [ ] Document runbooks
- [ ] Set up on-call rotation

## Additional Resources

- [Kong Documentation](https://docs.konghq.com/)
- [Kong Ingress Controller](https://github.com/Kong/kubernetes-ingress-controller)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [OAuth 2.1 Specification](https://oauth.net/2.1/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
