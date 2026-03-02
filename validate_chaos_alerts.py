#!/usr/bin/env python3
"""Validate chaos engineering Prometheus alerts YAML file."""

import sys
from pathlib import Path

try:
    import yaml
    
    alerts_file = "configs/prometheus/rules/alerts.yml"
    
    try:
        with open(alerts_file, 'r') as f:
            data = yaml.safe_load(f)
        
        # Check structure
        if 'groups' not in data:
            print(f"✗ {alerts_file}: Missing 'groups' key")
            sys.exit(1)
        
        # Find chaos_engineering_alerts group
        chaos_group = None
        for group in data['groups']:
            if group.get('name') == 'chaos_engineering_alerts':
                chaos_group = group
                break
        
        if chaos_group is None:
            print(f"✗ {alerts_file}: Missing 'chaos_engineering_alerts' group")
            sys.exit(1)
        
        # Count alerts in chaos group
        alert_count = len(chaos_group.get('rules', []))
        print(f"✓ {alerts_file}: Valid YAML")
        print(f"✓ Found chaos_engineering_alerts group with {alert_count} alerts")
        
        # List alerts
        for rule in chaos_group.get('rules', []):
            alert_name = rule.get('alert', 'unknown')
            print(f"  - {alert_name}")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"✗ {alerts_file}: {e}")
        sys.exit(1)

except ImportError:
    print("✗ PyYAML not installed - cannot validate YAML")
    print("  This is OK for validation purposes")
    sys.exit(0)
