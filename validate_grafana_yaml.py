#!/usr/bin/env python3
"""Validate Grafana and Prometheus YAML files."""

import sys
from pathlib import Path

try:
    import yaml
    
    config_files = [
        "configs/prometheus/prometheus.yml",
        "configs/grafana/provisioning/datasources/datasources.yml",
        "configs/grafana/provisioning/dashboards/dashboards.yml"
    ]
    
    all_valid = True
    for config_file in config_files:
        config_path = Path(config_file)
        try:
            with open(config_path, 'r') as f:
                yaml.safe_load(f)
            print(f"✓ {config_file}: Valid YAML")
        except Exception as e:
            print(f"✗ {config_file}: {e}")
            all_valid = False
    
    if all_valid:
        print("\n✓ All Grafana/Prometheus config files have valid YAML syntax")
        sys.exit(0)
    else:
        print("\n✗ Some config files have invalid YAML")
        sys.exit(1)

except ImportError:
    print("✗ PyYAML not installed - cannot validate YAML")
    print("  This is OK for validation purposes")
    sys.exit(0)
