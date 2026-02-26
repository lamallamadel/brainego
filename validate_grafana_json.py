#!/usr/bin/env python3
"""Validate Grafana dashboard JSON files."""

import json
import sys
from pathlib import Path

dashboard_dir = Path("configs/grafana/dashboards")
dashboards = [
    "drift-overview.json",
    "drift-kl-divergence.json",
    "drift-psi-trends.json",
    "drift-accuracy-tracking.json",
    "lora-version-tracking.json"
]

all_valid = True
for dashboard in dashboards:
    dashboard_path = dashboard_dir / dashboard
    try:
        with open(dashboard_path, 'r') as f:
            json.load(f)
        print(f"✓ {dashboard}: Valid JSON")
    except Exception as e:
        print(f"✗ {dashboard}: {e}")
        all_valid = False

if all_valid:
    print("\n✓ All Grafana dashboards have valid JSON syntax")
    sys.exit(0)
else:
    print("\n✗ Some dashboards have invalid JSON")
    sys.exit(1)
