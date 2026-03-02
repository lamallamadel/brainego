#!/usr/bin/env python3
"""Validate observability YAML files"""
import yaml
import sys

files = [
    'docker-compose.observability.yml',
    'configs/prometheus/prometheus.yml'
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
    print('\n✓ All observability YAML files are valid')
    sys.exit(0)
else:
    print('\n✗ Some YAML files have errors')
    sys.exit(1)
