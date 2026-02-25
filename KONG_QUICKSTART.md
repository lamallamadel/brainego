# Kong Ingress Controller - Quick Start Guide

This guide will get you up and running with Kong Ingress Controller in 10 minutes.

## Prerequisites

- Kubernetes cluster (1.24+)
- `kubectl` configured
- `helm` (3.10+)
- Domain name with DNS access
- `openssl` for key generation

## 1. Generate JWT Keys (2 minutes)

```bash
# Generate RSA key pair for JWT authentication
chmod +x generate-kong-jwt-keys.sh
./generate-kong-jwt-keys.sh kong-jwt-keys 4096

# Keys will be saved in kong-jwt-keys/
# DO NOT commit private key to git!
```

## 2. Configure Deployment (3 minutes)

Edit `helm/ai-platform/values.yaml`:

```yaml
kong:
  enabled: true
  
  ingress:
    host: api.your-domain.com  # ← Change this
  
  oauth2:
    adminClientId: <generate-uuid>  # ← Generate with: uuidgen
    adminClientSecret: <generate-secret>  # ← Generate with: openssl rand -base64 32
    provisionKey: <generate-provision-key>  # ← Generate with: openssl rand -base64 32
    redirectUri: https://your-domain.com/auth/callback  # ← Change this
  
  jwt:
    # Copy from kong-jwt-keys/kong-jwt-values.yaml
    privateKey: <base64-encoded-private-key>
    publicKey: <base64-encoded-public-key>

certManager:
  enabled: true
  email: admin@your-domain.com  # ← Change this
```

## 3. Deploy (5 minutes)

```bash
# Make deploy script executable
chmod +x deploy-kong.sh

# Deploy with environment variables
DOMAIN=api.your-domain.com \
EMAIL=admin@your-domain.com \
./deploy-kong.sh

# Or deploy manually
cd helm/ai-platform
helm dependency update
helm install ai-platform . \
  --namespace ai-platform \
  --create-namespace \
  --wait
```

## 4. Configure DNS

Get the LoadBalancer IP:

```bash
kubectl get svc -n ai-platform kong-proxy
```

Add DNS A records:
- `api.your-domain.com` → LoadBalancer IP
- `grafana.your-domain.com` → LoadBalancer IP

## 5. Wait for TLS Certificates

```bash
# Watch certificate status (takes 2-5 minutes)
kubectl get certificates -n ai-platform --watch

# Should show:
# NAME              READY   SECRET           AGE
# ai-platform-tls   True    ai-platform-tls  2m
# grafana-tls       True    grafana-tls      2m
```

## 6. Test Authentication

### Option A: Using JWT (Recommended)

```bash
# Generate JWT token
python3 generate_kong_jwt.py \
  --private-key kong-jwt-keys/kong-jwt-private.pem \
  --subject user-123 \
  --expiration 24

# Copy token and test
export JWT_TOKEN="<token-from-above>"

curl -H "Authorization: Bearer $JWT_TOKEN" \
  https://api.your-domain.com/v1/chat/completions \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Option B: Using OAuth2 Client Credentials

```bash
# Get access token
curl -X POST https://api.your-domain.com/oauth2/token \
  -d "grant_type=client_credentials" \
  -d "client_id=<your-client-id>" \
  -d "client_secret=<your-client-secret>" \
  -d "scope=api.read api.write"

# Use access token
export ACCESS_TOKEN="<token-from-response>"

curl -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.your-domain.com/v1/chat/completions \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## 7. Test Rate Limiting

```bash
# Test IP rate limit (100/minute)
chmod +x test-kong-auth.sh
./test-kong-auth.sh

# Or manually
for i in {1..105}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    https://api.your-domain.com/v1/chat/completions
done
# First 100: 200 OK
# After 100: 429 Too Many Requests
```

## 8. Monitor with Grafana

```bash
# Access Grafana
kubectl port-forward -n ai-platform svc/grafana 3000:3000

# Open: http://localhost:3000
# Username: admin
# Password: (from secrets.grafana.password in values.yaml)

# Import Kong dashboard:
# - Go to Dashboards → Import
# - Upload: configs/grafana/dashboards/kong-dashboard.json
```

## Features Enabled

✅ **OAuth 2.1** with PKCE
- Authorization Code Flow
- Client Credentials Flow
- Refresh Token support

✅ **JWT Authentication** (RS256)
- RSA 4096-bit keys
- Automatic validation
- Custom claims support

✅ **Multi-layer Rate Limiting**
- Layer 1: 100 requests/minute per IP
- Layer 2: 1000 requests/hour per user
- Layer 3: 10000 requests/day per workspace
- Layer 4: 1M token budget per workspace per day

✅ **TLS 1.3**
- Auto-provisioned by cert-manager
- Let's Encrypt certificates
- Automatic renewal

✅ **Structured Audit Logging**
- User ID tracking
- Token usage tracking
- Latency monitoring
- Model and tool tracking
- JSON format for easy parsing

## Next Steps

1. **Review Security Settings**
   - Update default passwords
   - Rotate JWT keys regularly
   - Configure network policies
   - See: KONG_DEPLOYMENT.md → Security section

2. **Set Up Monitoring**
   - Configure Prometheus alerts
   - Set up log aggregation
   - Enable audit log shipping
   - See: KONG_DEPLOYMENT.md → Monitoring section

3. **Create Additional Consumers**
   ```bash
   # Add new OAuth2 consumer
   kubectl apply -f - <<EOF
   apiVersion: configuration.konghq.com/v1
   kind: KongConsumer
   metadata:
     name: new-user
     namespace: ai-platform
   username: new-user
   EOF
   
   # Add OAuth2 credentials
   # See: KONG_DEPLOYMENT.md → Authentication section
   ```

4. **Configure Workspaces**
   - Set token budgets per workspace
   - Configure workspace-specific rate limits
   - See: configs/kong-config.yaml

5. **Production Hardening**
   - [ ] Update all secrets
   - [ ] Configure backup automation
   - [ ] Set up disaster recovery
   - [ ] Enable network policies
   - [ ] Configure pod security policies
   - [ ] Set resource limits
   - [ ] See: KONG_DEPLOYMENT.md → Production Checklist

## Troubleshooting

### Certificates Not Ready

```bash
# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager

# Check challenge status
kubectl describe challenge -n ai-platform

# Common issue: DNS not configured
# Make sure A records point to LoadBalancer IP
```

### Authentication Failing

```bash
# Check Kong logs
kubectl logs -n ai-platform -l app.kubernetes.io/name=kong

# Verify JWT public key
kubectl get secret kong-jwt-keypair -n ai-platform -o yaml

# Test JWT locally
python3 generate_kong_jwt.py \
  --decode "<your-token>" \
  --public-key kong-jwt-keys/kong-jwt-public.pem \
  --verify
```

### Rate Limiting Not Working

```bash
# Check Redis connection
kubectl exec -n ai-platform -it redis-0 -- redis-cli ping

# View rate limit keys
kubectl exec -n ai-platform -it redis-0 -- \
  redis-cli --scan --pattern "ratelimit:*"

# Check plugin configuration
kubectl get kongplugin -n ai-platform
```

## Common Commands

```bash
# View all Kong resources
kubectl get kong -n ai-platform

# Check ingress status
kubectl get ingress -n ai-platform

# View audit logs
kubectl logs -n ai-platform -l app.kubernetes.io/name=kong | grep audit

# Access Kong admin API
kubectl port-forward -n ai-platform svc/kong-admin 8001:8001
curl http://localhost:8001/status

# Restart Kong
kubectl rollout restart deployment/kong -n ai-platform
```

## Documentation

- Full deployment guide: [KONG_DEPLOYMENT.md](KONG_DEPLOYMENT.md)
- Authentication examples: [examples/kong_auth_client.py](examples/kong_auth_client.py)
- Configuration reference: [configs/kong-config.yaml](configs/kong-config.yaml)
- Kong docs: https://docs.konghq.com/

## Support

For issues or questions:
1. Check logs: `kubectl logs -n ai-platform -l app.kubernetes.io/name=kong`
2. Review configuration: `kubectl get kongplugin,kongconsumer,ingress -n ai-platform`
3. See troubleshooting guide: KONG_DEPLOYMENT.md → Troubleshooting section
