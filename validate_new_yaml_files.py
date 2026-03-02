#!/usr/bin/env python3
"""Validate new YAML files for multi-region deployment"""
import yaml
import sys

files = [
    'helm/ai-platform/values-multi-region.yaml',
    'configs/geo-routing.yaml',
    'configs/prometheus-multi-region.yaml',
    'configs/prometheus-alerts-multi-region.yaml'
]

all_valid = True

for filepath in files:
    try:
        with open(filepath, 'r') as f:
            yaml.safe_load(f)
        print(f'✓ {filepath} is valid')
    except Exception as e:
        print(f'✗ {filepath} failed: {e}')
        all_valid = False

if all_valid:
    print('\n✓ All new YAML files are valid')
    sys.exit(0)
else:
    print('\n✗ Some YAML files have errors')
    sys.exit(1)
