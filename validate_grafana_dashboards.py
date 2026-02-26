#!/usr/bin/env python3
"""Validate Grafana dashboard JSON files."""

import json
import sys
from pathlib import Path

def validate_json_file(file_path):
    """Validate a JSON file."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        print(f"✓ {file_path.name}: VALID JSON")
        return True
    except json.JSONDecodeError as e:
        print(f"✗ {file_path.name}: INVALID JSON - {e}")
        return False
    except Exception as e:
        print(f"✗ {file_path.name}: ERROR - {e}")
        return False

def main():
    """Validate all Grafana dashboard files."""
    dashboard_dir = Path("configs/grafana/dashboards")
    
    if not dashboard_dir.exists():
        print(f"✗ Directory not found: {dashboard_dir}")
        sys.exit(1)
    
    dashboards = [
        "platform-overview.json",
        "learning-engine.json",
        "mcp-activity.json"
    ]
    
    all_valid = True
    for dashboard in dashboards:
        file_path = dashboard_dir / dashboard
        if file_path.exists():
            if not validate_json_file(file_path):
                all_valid = False
        else:
            print(f"✗ {dashboard}: FILE NOT FOUND")
            all_valid = False
    
    # Validate metrics.py exists and is valid Python
    metrics_file = Path("learning_engine/metrics.py")
    if metrics_file.exists():
        try:
            with open(metrics_file, 'r') as f:
                compile(f.read(), metrics_file, 'exec')
            print(f"✓ {metrics_file}: VALID PYTHON")
        except SyntaxError as e:
            print(f"✗ {metrics_file}: SYNTAX ERROR - {e}")
            all_valid = False
    else:
        print(f"✗ {metrics_file}: FILE NOT FOUND")
        all_valid = False
    
    if all_valid:
        print("\n✓ All Grafana dashboard files are valid!")
        sys.exit(0)
    else:
        print("\n✗ Some files are invalid!")
        sys.exit(1)

if __name__ == "__main__":
    main()
