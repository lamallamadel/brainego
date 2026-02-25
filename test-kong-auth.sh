#!/bin/bash
# Test Kong OAuth 2.1 + JWT authentication and rate limiting

set -euo pipefail

DOMAIN="${DOMAIN:-api.your-domain.com}"
NAMESPACE="${NAMESPACE:-ai-platform}"

echo "=========================================="
echo "Kong Authentication & Rate Limiting Tests"
echo "=========================================="
echo "Domain: $DOMAIN"
echo "Namespace: $NAMESPACE"
echo ""

# Test 1: Health check (no auth required)
echo "Test 1: Health Check"
echo "--------------------"
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/health" || echo "000")
if [ "$HEALTH_STATUS" = "200" ]; then
    echo "✓ Health check passed (200 OK)"
else
    echo "✗ Health check failed (HTTP $HEALTH_STATUS)"
fi
echo ""

# Test 2: Unauthorized access
echo "Test 2: Unauthorized Access"
echo "---------------------------"
UNAUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/v1/chat/completions" || echo "000")
if [ "$UNAUTH_STATUS" = "401" ] || [ "$UNAUTH_STATUS" = "403" ]; then
    echo "✓ Unauthorized access blocked (HTTP $UNAUTH_STATUS)"
else
    echo "⚠ Unexpected response (HTTP $UNAUTH_STATUS)"
fi
echo ""

# Test 3: OAuth2 Authorization Flow
echo "Test 3: OAuth2 Authorization Flow"
echo "----------------------------------"
echo "This requires interactive authentication."
echo "OAuth2 endpoint: https://$DOMAIN/oauth2/authorize"
echo ""
echo "Example authorization URL:"
CLIENT_ID="${CLIENT_ID:-admin-client-id}"
cat <<EOF
https://$DOMAIN/oauth2/authorize?response_type=code&client_id=$CLIENT_ID&redirect_uri=https://$DOMAIN/auth/callback&scope=api.read+api.write&code_challenge=CHALLENGE&code_challenge_method=S256
EOF
echo ""

# Test 4: Generate and test JWT
echo "Test 4: JWT Generation & Testing"
echo "---------------------------------"
if command -v python3 >/dev/null 2>&1 && python3 -c "import jwt" 2>/dev/null; then
    echo "Generating JWT token..."
    
    # Create test JWT generator script
    cat > /tmp/generate_jwt.py <<'EOPY'
import jwt
import datetime
import sys

if len(sys.argv) < 2:
    print("Usage: python3 generate_jwt.py <private_key_path>")
    sys.exit(1)

with open(sys.argv[1], 'r') as f:
    private_key = f.read()

payload = {
    'iss': 'admin-key',
    'sub': 'test-user',
    'aud': 'ai-platform',
    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1),
    'nbf': datetime.datetime.utcnow(),
    'iat': datetime.datetime.utcnow(),
    'kid': 'admin-key',
    'scopes': ['api.read', 'api.write']
}

token = jwt.encode(payload, private_key, algorithm='RS256')
print(token)
EOPY
    
    if [ -f kong-jwt-keys/kong-jwt-private.pem ]; then
        JWT_TOKEN=$(python3 /tmp/generate_jwt.py kong-jwt-keys/kong-jwt-private.pem)
        echo "✓ JWT token generated"
        echo ""
        echo "Testing API with JWT..."
        
        JWT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer $JWT_TOKEN" \
            "https://$DOMAIN/v1/chat/completions" || echo "000")
        
        if [ "$JWT_STATUS" = "200" ] || [ "$JWT_STATUS" = "400" ]; then
            echo "✓ JWT authentication successful (HTTP $JWT_STATUS)"
        else
            echo "✗ JWT authentication failed (HTTP $JWT_STATUS)"
        fi
    else
        echo "⚠ JWT private key not found at kong-jwt-keys/kong-jwt-private.pem"
    fi
    
    rm -f /tmp/generate_jwt.py
else
    echo "⚠ Python3 with PyJWT not available, skipping JWT test"
    echo "Install with: pip3 install pyjwt cryptography"
fi
echo ""

# Test 5: Rate Limiting
echo "Test 5: Rate Limiting (IP-based)"
echo "--------------------------------"
if [ -n "${JWT_TOKEN:-}" ]; then
    echo "Sending 105 requests to test rate limit (100/min)..."
    SUCCESS_COUNT=0
    RATE_LIMITED_COUNT=0
    
    for i in {1..105}; do
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "Authorization: Bearer $JWT_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"messages": [{"role": "user", "content": "test"}]}' \
            "https://$DOMAIN/v1/chat/completions" 2>/dev/null || echo "000")
        
        if [ "$STATUS" = "200" ] || [ "$STATUS" = "400" ]; then
            ((SUCCESS_COUNT++))
        elif [ "$STATUS" = "429" ]; then
            ((RATE_LIMITED_COUNT++))
        fi
        
        # Show progress every 20 requests
        if [ $((i % 20)) -eq 0 ]; then
            echo "  Sent $i requests: $SUCCESS_COUNT successful, $RATE_LIMITED_COUNT rate-limited"
        fi
    done
    
    echo ""
    echo "Results after 105 requests:"
    echo "  Successful: $SUCCESS_COUNT"
    echo "  Rate Limited: $RATE_LIMITED_COUNT"
    
    if [ $RATE_LIMITED_COUNT -gt 0 ]; then
        echo "✓ Rate limiting working (blocked after ~100 requests)"
    else
        echo "⚠ Rate limiting may not be configured correctly"
    fi
else
    echo "⚠ Skipping rate limit test (no JWT token available)"
fi
echo ""

# Test 6: Check Rate Limit Headers
echo "Test 6: Rate Limit Headers"
echo "--------------------------"
if [ -n "${JWT_TOKEN:-}" ]; then
    echo "Checking rate limit headers..."
    curl -I -s -H "Authorization: Bearer $JWT_TOKEN" \
        "https://$DOMAIN/v1/chat/completions" 2>/dev/null | grep -i "ratelimit" || echo "No rate limit headers found"
else
    echo "⚠ Skipping (no JWT token available)"
fi
echo ""

# Test 7: Token Budget Headers
echo "Test 7: Token Budget Headers"
echo "----------------------------"
if [ -n "${JWT_TOKEN:-}" ]; then
    echo "Checking token budget headers..."
    curl -I -s -H "Authorization: Bearer $JWT_TOKEN" \
        -H "X-Workspace-Id: test-workspace" \
        "https://$DOMAIN/v1/chat/completions" 2>/dev/null | grep -i "token-budget" || echo "No token budget headers found"
else
    echo "⚠ Skipping (no JWT token available)"
fi
echo ""

# Test 8: Correlation ID
echo "Test 8: Correlation ID Header"
echo "-----------------------------"
if [ -n "${JWT_TOKEN:-}" ]; then
    echo "Checking correlation ID header..."
    CORR_ID=$(curl -I -s -H "Authorization: Bearer $JWT_TOKEN" \
        "https://$DOMAIN/v1/chat/completions" 2>/dev/null | grep -i "x-request-id" || echo "")
    if [ -n "$CORR_ID" ]; then
        echo "✓ Correlation ID present"
        echo "$CORR_ID"
    else
        echo "⚠ Correlation ID header not found"
    fi
else
    echo "⚠ Skipping (no JWT token available)"
fi
echo ""

# Test 9: TLS Configuration
echo "Test 9: TLS 1.3 Configuration"
echo "-----------------------------"
if command -v openssl >/dev/null 2>&1; then
    echo "Checking TLS version and ciphers..."
    TLS_INFO=$(echo | openssl s_client -connect "$DOMAIN:443" -tls1_3 2>/dev/null | grep -E "Protocol|Cipher" || echo "")
    if [ -n "$TLS_INFO" ]; then
        echo "$TLS_INFO"
        if echo "$TLS_INFO" | grep -q "TLSv1.3"; then
            echo "✓ TLS 1.3 is supported"
        else
            echo "⚠ TLS 1.3 not detected"
        fi
    else
        echo "⚠ Could not determine TLS configuration"
    fi
else
    echo "⚠ OpenSSL not available, skipping TLS test"
fi
echo ""

# Test 10: Prometheus Metrics
echo "Test 10: Prometheus Metrics"
echo "---------------------------"
if [ -n "${JWT_TOKEN:-}" ]; then
    METRICS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "https://$DOMAIN/metrics" 2>/dev/null || echo "000")
    
    if [ "$METRICS_STATUS" = "200" ]; then
        echo "✓ Metrics endpoint accessible (HTTP 200)"
    else
        echo "⚠ Metrics endpoint returned HTTP $METRICS_STATUS"
    fi
else
    echo "⚠ Skipping (no JWT token available)"
fi
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "Basic Tests:"
echo "  ✓ Tests completed"
echo ""
echo "Authentication:"
if [ -n "${JWT_TOKEN:-}" ]; then
    echo "  ✓ JWT authentication tested"
else
    echo "  ⚠ JWT authentication not tested (PyJWT not available)"
fi
echo ""
echo "Rate Limiting:"
if [ -n "${JWT_TOKEN:-}" ] && [ ${RATE_LIMITED_COUNT:-0} -gt 0 ]; then
    echo "  ✓ Rate limiting verified"
else
    echo "  ⚠ Rate limiting not fully verified"
fi
echo ""
echo "Security:"
if echo "$TLS_INFO" | grep -q "TLSv1.3" 2>/dev/null; then
    echo "  ✓ TLS 1.3 enabled"
else
    echo "  ⚠ TLS configuration not verified"
fi
echo ""
echo "For production use:"
echo "  1. Update OAuth2 client credentials"
echo "  2. Rotate JWT keys regularly"
echo "  3. Configure monitoring alerts"
echo "  4. Review audit logs regularly"
echo ""
echo "See KONG_DEPLOYMENT.md for detailed documentation"
echo ""
