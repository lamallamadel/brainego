#!/usr/bin/env python3
"""Validate VPA automation implementation."""

import json
import sys
from pathlib import Path

def validate_dashboard():
    """Validate cost-optimization dashboard JSON."""
    dashboard_path = Path("configs/grafana/dashboards/cost-optimization.json")
    
    try:
        with open(dashboard_path, 'r') as f:
            dashboard = json.load(f)
        
        panels = dashboard.get("panels", [])
        print(f"✓ Cost-optimization dashboard valid: {len(panels)} panels")
        
        # Check for VPA panels (IDs 8-12 should be VPA-related)
        vpa_panel_count = 0
        for panel in panels:
            if panel.get("id", 0) >= 8:
                title = panel.get("title", "")
                if "VPA" in title or "vpa" in title.lower():
                    vpa_panel_count += 1
                    print(f"  - Found VPA panel: {title}")
        
        if vpa_panel_count >= 5:
            print(f"✓ Found {vpa_panel_count} VPA panels (expected 5)")
        else:
            print(f"⚠ Found only {vpa_panel_count} VPA panels (expected 5)")
        
        return True
    except Exception as e:
        print(f"✗ Dashboard validation failed: {e}")
        return False

def validate_helm_template():
    """Validate VPA helm template exists."""
    template_path = Path("helm/ai-platform/templates/vpa.yaml")
    
    if not template_path.exists():
        print(f"✗ VPA helm template not found: {template_path}")
        return False
    
    with open(template_path, 'r') as f:
        content = f.read()
    
    # Count VPA resources
    vpa_count = content.count("kind: VerticalPodAutoscaler")
    print(f"✓ VPA helm template found: {vpa_count} VPA resources")
    
    # Check for key services
    required_services = ["api-server", "gateway", "mcpjungle", "redis", "qdrant", "postgres"]
    found_services = []
    for service in required_services:
        if f"name: {service}-vpa" in content:
            found_services.append(service)
    
    print(f"✓ Found {len(found_services)}/{len(required_services)} required VPA services")
    
    return True

def validate_scripts():
    """Validate VPA automation scripts exist."""
    scripts = [
        "scripts/observability/apply_vpa_recommendations.py",
        "scripts/observability/vpa_automation_workflow.sh",
        "scripts/observability/test_vpa_automation.py"
    ]
    
    all_exist = True
    for script in scripts:
        script_path = Path(script)
        if script_path.exists():
            size = script_path.stat().st_size
            print(f"✓ {script} exists ({size} bytes)")
        else:
            print(f"✗ {script} not found")
            all_exist = False
    
    return all_exist

def validate_documentation():
    """Validate documentation files exist."""
    docs = [
        "scripts/observability/README_VPA.md",
        "scripts/observability/VPA_QUICKSTART.md",
        "VPA_AUTOMATION_IMPLEMENTATION.md"
    ]
    
    all_exist = True
    for doc in docs:
        doc_path = Path(doc)
        if doc_path.exists():
            with open(doc_path, 'r', encoding='utf-8') as f:
                lines = len(f.readlines())
            print(f"✓ {doc} exists ({lines} lines)")
        else:
            print(f"✗ {doc} not found")
            all_exist = False
    
    return all_exist

def main():
    """Run all validations."""
    print("=" * 80)
    print("VPA Automation Implementation Validation")
    print("=" * 80)
    print()
    
    results = []
    
    print("1. Validating Grafana Dashboard...")
    results.append(validate_dashboard())
    print()
    
    print("2. Validating Helm Template...")
    results.append(validate_helm_template())
    print()
    
    print("3. Validating Scripts...")
    results.append(validate_scripts())
    print()
    
    print("4. Validating Documentation...")
    results.append(validate_documentation())
    print()
    
    print("=" * 80)
    if all(results):
        print("✓ All validations passed")
        print("=" * 80)
        return 0
    else:
        print("✗ Some validations failed")
        print("=" * 80)
        return 1

if __name__ == "__main__":
    sys.exit(main())
