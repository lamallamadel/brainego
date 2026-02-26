#!/usr/bin/env python3
"""Validate Kong implementation files."""

import json
import sys
from pathlib import Path

print("Validating Kong implementation files...")
print()

# Validate JSON files
json_files = [
    "configs/grafana/dashboards/kong-dashboard.json"
]

all_valid = True

for json_file in json_files:
    json_path = Path(json_file)
    if json_path.exists():
        try:
            with open(json_path, 'r') as f:
                json.load(f)
            print(f"✓ {json_file}: Valid JSON")
        except Exception as e:
            print(f"✗ {json_file}: {e}")
            all_valid = False
    else:
        print(f"⚠ {json_file}: File not found")

print()

# Check for required Python files
python_files = [
    "generate_kong_jwt.py",
    "examples/kong_auth_client.py"
]

for py_file in python_files:
    py_path = Path(py_file)
    if py_path.exists():
        print(f"✓ {py_file}: File exists")
    else:
        print(f"✗ {py_file}: File not found")
        all_valid = False

print()

# Check for shell scripts
shell_scripts = [
    "generate-kong-jwt-keys.sh",
    "deploy-kong.sh",
    "test-kong-auth.sh",
    "manage-kong.sh",
    "setup-kong-scripts.sh"
]

for script in shell_scripts:
    script_path = Path(script)
    if script_path.exists():
        print(f"✓ {script}: File exists")
    else:
        print(f"✗ {script}: File not found")
        all_valid = False

print()

# Check for Helm templates
helm_templates = [
    "helm/ai-platform/templates/kong-ingress.yaml",
    "helm/ai-platform/templates/kong-oauth2-consumers.yaml",
    "helm/ai-platform/templates/cert-manager-issuer.yaml",
    "helm/ai-platform/templates/kong-custom-plugins.yaml"
]

for template in helm_templates:
    template_path = Path(template)
    if template_path.exists():
        print(f"✓ {template}: File exists")
    else:
        print(f"✗ {template}: File not found")
        all_valid = False

print()

# Check for documentation
docs = [
    "KONG_DEPLOYMENT.md",
    "KONG_QUICKSTART.md",
    "KONG_IMPLEMENTATION_SUMMARY.md",
    "KONG_FILES_CREATED.md",
    "KONG_COMPLETE.md",
    "KONG_README.md"
]

for doc in docs:
    doc_path = Path(doc)
    if doc_path.exists():
        print(f"✓ {doc}: File exists")
    else:
        print(f"✗ {doc}: File not found")
        all_valid = False

print()

if all_valid:
    print("✓ All Kong implementation files validated successfully")
    sys.exit(0)
else:
    print("✗ Some validation checks failed")
    sys.exit(1)
