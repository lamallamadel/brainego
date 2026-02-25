#!/bin/bash
# Generate RSA key pair for Kong JWT authentication (RS256)

set -euo pipefail

OUTPUT_DIR="${1:-./kong-jwt-keys}"
KEY_SIZE="${2:-4096}"

echo "Generating RSA key pair for Kong JWT (RS256)..."
echo "Output directory: $OUTPUT_DIR"
echo "Key size: $KEY_SIZE bits"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate private key
echo "Generating private key..."
openssl genrsa -out "$OUTPUT_DIR/kong-jwt-private.pem" "$KEY_SIZE"

# Generate public key
echo "Generating public key..."
openssl rsa -in "$OUTPUT_DIR/kong-jwt-private.pem" -pubout -out "$OUTPUT_DIR/kong-jwt-public.pem"

# Base64 encode for Kubernetes secrets
echo "Encoding keys to base64..."
PRIVATE_KEY_B64=$(base64 -w 0 "$OUTPUT_DIR/kong-jwt-private.pem" 2>/dev/null || base64 "$OUTPUT_DIR/kong-jwt-private.pem")
PUBLIC_KEY_B64=$(base64 -w 0 "$OUTPUT_DIR/kong-jwt-public.pem" 2>/dev/null || base64 "$OUTPUT_DIR/kong-jwt-public.pem")

# Save base64 encoded keys
echo "$PRIVATE_KEY_B64" > "$OUTPUT_DIR/kong-jwt-private.b64"
echo "$PUBLIC_KEY_B64" > "$OUTPUT_DIR/kong-jwt-public.b64"

# Generate values.yaml snippet
cat > "$OUTPUT_DIR/kong-jwt-values.yaml" <<EOF
# Kong JWT Configuration
# Add this to your helm/ai-platform/values.yaml file

kong:
  jwt:
    privateKey: $PRIVATE_KEY_B64
    publicKey: $PUBLIC_KEY_B64
EOF

# Display results
echo ""
echo "✓ RSA key pair generated successfully!"
echo ""
echo "Files created in $OUTPUT_DIR:"
echo "  - kong-jwt-private.pem (Private key - KEEP SECURE!)"
echo "  - kong-jwt-public.pem (Public key)"
echo "  - kong-jwt-private.b64 (Base64 encoded private key)"
echo "  - kong-jwt-public.b64 (Base64 encoded public key)"
echo "  - kong-jwt-values.yaml (Helm values snippet)"
echo ""
echo "Next steps:"
echo "1. Keep kong-jwt-private.pem SECURE and DO NOT commit to git"
echo "2. Update helm/ai-platform/values.yaml with the values from kong-jwt-values.yaml"
echo "3. Or use as Kubernetes secret:"
echo ""
echo "kubectl create secret generic kong-jwt-keypair \\"
echo "  --from-file=private_key=$OUTPUT_DIR/kong-jwt-private.pem \\"
echo "  --from-file=public_key=$OUTPUT_DIR/kong-jwt-public.pem \\"
echo "  --namespace ai-platform"
echo ""

# Add to .gitignore
if [ -f .gitignore ]; then
    if ! grep -q "kong-jwt-keys" .gitignore; then
        echo "kong-jwt-keys/" >> .gitignore
        echo "✓ Added kong-jwt-keys/ to .gitignore"
    fi
fi

# Set secure permissions
chmod 600 "$OUTPUT_DIR/kong-jwt-private.pem"
chmod 644 "$OUTPUT_DIR/kong-jwt-public.pem"

echo "✓ Set secure file permissions"
echo ""
echo "Done!"
