#!/bin/bash
# Make all Kong scripts executable

set -euo pipefail

echo "Making Kong scripts executable..."

# Scripts to make executable
SCRIPTS=(
    "generate-kong-jwt-keys.sh"
    "deploy-kong.sh"
    "test-kong-auth.sh"
    "manage-kong.sh"
    "setup-kong-scripts.sh"
)

for script in "${SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        chmod +x "$script"
        echo "✓ Made $script executable"
    else
        echo "⚠ Script not found: $script"
    fi
done

# Make Python scripts executable
PYTHON_SCRIPTS=(
    "generate_kong_jwt.py"
    "examples/kong_auth_client.py"
)

for script in "${PYTHON_SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        chmod +x "$script"
        echo "✓ Made $script executable"
    else
        echo "⚠ Script not found: $script"
    fi
done

echo ""
echo "✓ All Kong scripts are now executable!"
echo ""
echo "Next steps:"
echo "1. Generate JWT keys:     ./generate-kong-jwt-keys.sh"
echo "2. Deploy Kong:           ./deploy-kong.sh"
echo "3. Test deployment:       ./test-kong-auth.sh"
echo "4. Manage Kong:           ./manage-kong.sh help"
echo ""
echo "For quick start, see: KONG_QUICKSTART.md"
echo "For full guide, see:  KONG_DEPLOYMENT.md"
