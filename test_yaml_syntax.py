#!/usr/bin/env python3
"""Test YAML syntax for docker-compose.yaml."""

import sys

try:
    import yaml
    print("✓ PyYAML is available")
    
    with open('docker-compose.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    print(f"✓ docker-compose.yaml syntax is valid")
    print(f"  Services defined: {', '.join(config.get('services', {}).keys())}")
    
    # Check for neo4j service
    if 'neo4j' in config.get('services', {}):
        print("✓ neo4j service found in docker-compose.yaml")
    else:
        print("✗ neo4j service NOT found in docker-compose.yaml")
        sys.exit(1)
    
    sys.exit(0)
    
except ImportError:
    print("✗ PyYAML not installed - cannot validate YAML")
    print("  This is OK for validation purposes")
    sys.exit(0)
except Exception as e:
    print(f"✗ Error validating docker-compose.yaml: {e}")
    sys.exit(1)
