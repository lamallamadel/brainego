#!/bin/bash
# Deploy Kong Ingress Controller with OAuth 2.1 + JWT Authentication

set -euo pipefail

NAMESPACE="${NAMESPACE:-ai-platform}"
DOMAIN="${DOMAIN:-api.your-domain.com}"
EMAIL="${EMAIL:-admin@your-domain.com}"

echo "=========================================="
echo "Kong Ingress Controller Deployment"
echo "=========================================="
echo "Namespace: $NAMESPACE"
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
command -v kubectl >/dev/null 2>&1 || { echo "Error: kubectl not found"; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "Error: helm not found"; exit 1; }
echo "✓ kubectl and helm found"

# Check if namespace exists
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
    echo "Creating namespace $NAMESPACE..."
    kubectl create namespace "$NAMESPACE"
fi
echo "✓ Namespace ready"

# Add Helm repositories
echo ""
echo "Adding Helm repositories..."
helm repo add kong https://charts.konghq.com
helm repo add jetstack https://charts.jetstack.io
helm repo update
echo "✓ Helm repositories added"

# Install cert-manager first (if not already installed)
echo ""
echo "Checking cert-manager installation..."
if ! kubectl get namespace cert-manager >/dev/null 2>&1; then
    echo "Installing cert-manager..."
    helm install cert-manager jetstack/cert-manager \
        --namespace cert-manager \
        --create-namespace \
        --version v1.13.3 \
        --set installCRDs=true \
        --wait
    echo "✓ cert-manager installed"
else
    echo "✓ cert-manager already installed"
fi

# Wait for cert-manager to be ready
echo "Waiting for cert-manager to be ready..."
kubectl wait --for=condition=available --timeout=300s \
    deployment/cert-manager -n cert-manager
kubectl wait --for=condition=available --timeout=300s \
    deployment/cert-manager-webhook -n cert-manager
kubectl wait --for=condition=available --timeout=300s \
    deployment/cert-manager-cainjector -n cert-manager
echo "✓ cert-manager is ready"

# Update Helm chart dependencies
echo ""
echo "Updating Helm chart dependencies..."
cd helm/ai-platform
helm dependency update
cd ../..
echo "✓ Dependencies updated"

# Generate secrets if not exist
echo ""
echo "Checking for secrets..."

# Generate OAuth2 secrets
if ! kubectl get secret kong-oauth2-credentials -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "Generating OAuth2 secrets..."
    ADMIN_CLIENT_ID=$(uuidgen || openssl rand -hex 16)
    ADMIN_CLIENT_SECRET=$(openssl rand -base64 32)
    PROVISION_KEY=$(openssl rand -base64 32)
    
    echo "✓ OAuth2 secrets generated"
    echo "  Client ID: $ADMIN_CLIENT_ID"
    echo "  Client Secret: $ADMIN_CLIENT_SECRET (KEEP SECURE!)"
    echo "  Provision Key: $PROVISION_KEY (KEEP SECURE!)"
else
    echo "✓ OAuth2 secrets already exist"
fi

# Check for JWT keys
if [ ! -f kong-jwt-keys/kong-jwt-private.pem ]; then
    echo ""
    echo "JWT keys not found. Generating..."
    bash generate-kong-jwt-keys.sh kong-jwt-keys 4096
fi
echo "✓ JWT keys ready"

# Create values override file
echo ""
echo "Creating deployment values..."
cat > kong-deployment-values.yaml <<EOF
global:
  namespace: $NAMESPACE

kong:
  enabled: true
  
  ingress:
    host: $DOMAIN
  
  oauth2:
    adminClientId: ${ADMIN_CLIENT_ID:-admin-client-id-change-in-production}
    adminClientSecret: ${ADMIN_CLIENT_SECRET:-admin-client-secret-change-in-production}
    provisionKey: ${PROVISION_KEY:-provision-key-change-in-production}
    redirectUri: https://$DOMAIN/auth/callback
  
  jwt:
    privateKey: $(cat kong-jwt-keys/kong-jwt-private.b64 2>/dev/null || echo "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQ==")
    publicKey: $(cat kong-jwt-keys/kong-jwt-public.b64 2>/dev/null || echo "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0=")

certManager:
  enabled: true
  email: $EMAIL
EOF

echo "✓ Deployment values created"

# Deploy the Helm chart
echo ""
echo "Deploying AI Platform with Kong Ingress Controller..."
helm upgrade --install ai-platform helm/ai-platform \
    --namespace "$NAMESPACE" \
    --values kong-deployment-values.yaml \
    --wait \
    --timeout 15m

echo ""
echo "✓ Deployment complete!"

# Get status
echo ""
echo "=========================================="
echo "Deployment Status"
echo "=========================================="

# Get Kong proxy service
KONG_PROXY_IP=$(kubectl get svc -n "$NAMESPACE" kong-proxy -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending")
KONG_PROXY_HOSTNAME=$(kubectl get svc -n "$NAMESPACE" kong-proxy -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")

echo ""
echo "Kong Proxy Service:"
if [ "$KONG_PROXY_IP" != "pending" ]; then
    echo "  IP: $KONG_PROXY_IP"
elif [ -n "$KONG_PROXY_HOSTNAME" ]; then
    echo "  Hostname: $KONG_PROXY_HOSTNAME"
else
    echo "  Status: Pending (waiting for LoadBalancer)"
fi

# Get certificate status
echo ""
echo "TLS Certificates:"
kubectl get certificates -n "$NAMESPACE" -o wide

# Get ingress status
echo ""
echo "Ingress Resources:"
kubectl get ingress -n "$NAMESPACE"

# DNS configuration
echo ""
echo "=========================================="
echo "Next Steps"
echo "=========================================="
echo ""
echo "1. Configure DNS:"
echo "   Add A record: $DOMAIN -> ${KONG_PROXY_IP:-<LoadBalancer IP>}"
echo "   Add A record: grafana.$DOMAIN -> ${KONG_PROXY_IP:-<LoadBalancer IP>}"
echo ""
echo "2. Wait for TLS certificates to be issued (may take a few minutes):"
echo "   kubectl get certificates -n $NAMESPACE --watch"
echo ""
echo "3. Test the deployment:"
echo "   curl https://$DOMAIN/health"
echo ""
echo "4. Get OAuth2 access token:"
echo "   See KONG_DEPLOYMENT.md for authentication examples"
echo ""
echo "5. Monitor deployment:"
echo "   kubectl get pods -n $NAMESPACE"
echo "   kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=kong"
echo ""
echo "For detailed usage instructions, see KONG_DEPLOYMENT.md"
echo ""

# Save deployment info
cat > kong-deployment-info.txt <<EOF
Kong Ingress Controller Deployment Info
========================================

Deployment Date: $(date)
Namespace: $NAMESPACE
Domain: $DOMAIN
Email: $EMAIL

Services:
- API: https://$DOMAIN
- Grafana: https://grafana.$DOMAIN
- Kong Proxy: ${KONG_PROXY_IP:-pending}

OAuth2 Credentials:
- Client ID: ${ADMIN_CLIENT_ID:-<see kubernetes secret>}
- Client Secret: ${ADMIN_CLIENT_SECRET:-<see kubernetes secret>}
- Provision Key: ${PROVISION_KEY:-<see kubernetes secret>}

JWT Keys:
- Private Key: kong-jwt-keys/kong-jwt-private.pem
- Public Key: kong-jwt-keys/kong-jwt-public.pem

Endpoints:
- Chat Completions: POST https://$DOMAIN/v1/chat/completions
- Embeddings: POST https://$DOMAIN/v1/embeddings
- Gateway: https://$DOMAIN/gateway
- MCP: https://$DOMAIN/mcp
- Memory: https://$DOMAIN/memory
- Learning: https://$DOMAIN/learning
- Metrics: https://$DOMAIN/metrics

Rate Limits:
- IP: 100 requests/minute
- User: 1000 requests/hour
- Workspace: 10000 requests/day
- Token Budget: 1000000 tokens/day

For more information, see KONG_DEPLOYMENT.md
EOF

echo "✓ Deployment information saved to kong-deployment-info.txt"
echo ""
echo "Deployment complete! 🚀"
