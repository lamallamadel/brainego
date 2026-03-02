#!/usr/bin/env python3
"""
Manual Alert Trigger Script for Testing AlertManager Integration

This script sends test alerts directly to Prometheus Alertmanager to verify
alert routing, Slack integration, email delivery, and on-call rotation.

Usage:
    python scripts/trigger_test_alert.py --alert-type kong-rate-limit
    python scripts/trigger_test_alert.py --alert-type circuit-breaker --severity critical
    python scripts/trigger_test_alert.py --alert-type drift-detected
    python scripts/trigger_test_alert.py --alert-type memory-pressure
    python scripts/trigger_test_alert.py --list-alerts
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List

try:
    import requests
except ImportError:
    print("Error: requests library not found")
    print("Install with: pip install requests")
    sys.exit(1)


ALERT_TEMPLATES = {
    "kong-rate-limit": {
        "alertname": "KongRateLimitExceeded",
        "severity": "warning",
        "component": "kong",
        "summary": "Kong rate limit exceeded (TEST ALERT)",
        "description": "Test alert: Kong route /api/v1/chat is experiencing rate limit rejections at 15 requests/sec",
        "labels": {
            "route": "/api/v1/chat",
            "consumer": "test-consumer",
        },
    },
    "circuit-breaker": {
        "alertname": "CircuitBreakerOpen",
        "severity": "warning",
        "component": "circuit-breaker",
        "summary": "Circuit breaker is open (TEST ALERT)",
        "description": "Test alert: Circuit breaker 'max-serve-breaker' is in OPEN state for service max-serve-llama",
        "labels": {
            "name": "max-serve-breaker",
            "service": "max-serve-llama",
        },
    },
    "pod-restart": {
        "alertname": "PodRestartRateHigh",
        "severity": "warning",
        "component": "kubernetes",
        "summary": "High pod restart rate detected (TEST ALERT)",
        "description": "Test alert: Pod ai-platform/gateway-abc123 has restart rate of 0.15 restarts/sec",
        "labels": {
            "namespace": "ai-platform",
            "pod": "gateway-abc123",
            "container": "gateway",
        },
    },
    "memory-pressure": {
        "alertname": "MemoryPressureDetected",
        "severity": "warning",
        "component": "kubernetes",
        "summary": "Memory pressure detected (TEST ALERT)",
        "description": "Test alert: Container ai-platform/max-serve-llama-xyz/max-serve is using 92% of memory limit",
        "labels": {
            "namespace": "ai-platform",
            "pod": "max-serve-llama-xyz",
            "container": "max-serve",
        },
    },
    "drift-detected": {
        "alertname": "DriftDetected",
        "severity": "warning",
        "component": "drift-monitor",
        "summary": "Model drift detected (TEST ALERT)",
        "description": "Test alert: Model llama-3.3-8b drift score is 0.18 - model performance may be degrading",
        "labels": {
            "model": "llama-3.3-8b",
        },
    },
    "critical-service-down": {
        "alertname": "ServiceDown",
        "severity": "critical",
        "component": "infrastructure",
        "summary": "Service is down (TEST ALERT)",
        "description": "Test alert: api-server has been down for more than 2 minutes",
        "labels": {
            "job": "api-server",
        },
    },
}


def get_alertmanager_url() -> str:
    """Get AlertManager URL from environment or default."""
    default_url = "http://localhost:9093"
    return os.getenv("ALERTMANAGER_URL", default_url)


def create_alert_payload(
    alert_type: str,
    severity: str = None,
    custom_labels: Dict[str, str] = None,
) -> List[Dict]:
    """Create alert payload for Alertmanager API."""
    if alert_type not in ALERT_TEMPLATES:
        raise ValueError(f"Unknown alert type: {alert_type}")
    
    template = ALERT_TEMPLATES[alert_type].copy()
    
    # Override severity if provided
    if severity:
        template["severity"] = severity
    
    # Build labels
    labels = {
        "alertname": template["alertname"],
        "severity": template["severity"],
        "component": template["component"],
        "cluster": "ai-platform",
        "environment": "test",
    }
    
    # Add template-specific labels
    if "labels" in template:
        labels.update(template["labels"])
    
    # Add custom labels
    if custom_labels:
        labels.update(custom_labels)
    
    # Build annotations
    annotations = {
        "summary": template["summary"],
        "description": template["description"],
        "runbook_url": "https://docs.ai-platform.local/runbooks/test-alert",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # Create alert
    alert = {
        "labels": labels,
        "annotations": annotations,
        "startsAt": datetime.now(timezone.utc).isoformat(),
        "generatorURL": "http://prometheus:9090/alerts",
    }
    
    return [alert]


def send_alert(alertmanager_url: str, alert_payload: List[Dict]) -> bool:
    """Send alert to Alertmanager."""
    url = f"{alertmanager_url}/api/v1/alerts"
    
    try:
        print(f"Sending alert to {url}...")
        print(f"Payload: {json.dumps(alert_payload, indent=2)}")
        
        response = requests.post(
            url,
            json=alert_payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        
        if response.status_code == 200:
            print("✅ Alert sent successfully!")
            print(f"Response: {response.text}")
            return True
        else:
            print(f"❌ Failed to send alert: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
    
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection error: Could not connect to {url}")
        print("Make sure AlertManager is running and accessible.")
        return False
    except requests.exceptions.Timeout:
        print(f"❌ Timeout: Request to {url} timed out")
        return False
    except Exception as e:
        print(f"❌ Error sending alert: {e}")
        return False


def resolve_alert(alertmanager_url: str, alert_payload: List[Dict]) -> bool:
    """Send alert resolution to Alertmanager."""
    url = f"{alertmanager_url}/api/v1/alerts"
    
    # Add endsAt timestamp to resolve the alert
    for alert in alert_payload:
        alert["endsAt"] = datetime.now(timezone.utc).isoformat()
    
    try:
        print(f"Resolving alert...")
        response = requests.post(
            url,
            json=alert_payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        
        if response.status_code == 200:
            print("✅ Alert resolved successfully!")
            return True
        else:
            print(f"❌ Failed to resolve alert: HTTP {response.status_code}")
            return False
    
    except Exception as e:
        print(f"❌ Error resolving alert: {e}")
        return False


def list_alerts():
    """List available test alert types."""
    print("\n📋 Available Test Alert Types:\n")
    for alert_type, template in ALERT_TEMPLATES.items():
        print(f"  • {alert_type}")
        print(f"    Alert: {template['alertname']}")
        print(f"    Severity: {template['severity']}")
        print(f"    Component: {template['component']}")
        print(f"    Summary: {template['summary']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Trigger test alerts to verify AlertManager integration"
    )
    parser.add_argument(
        "--alert-type",
        type=str,
        help="Type of alert to trigger (e.g., kong-rate-limit, circuit-breaker)",
    )
    parser.add_argument(
        "--severity",
        type=str,
        choices=["warning", "critical"],
        help="Override alert severity (warning or critical)",
    )
    parser.add_argument(
        "--custom-label",
        type=str,
        action="append",
        help="Add custom label (format: key=value)",
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Send alert resolution after 10 seconds",
    )
    parser.add_argument(
        "--list-alerts",
        action="store_true",
        help="List available test alert types",
    )
    parser.add_argument(
        "--alertmanager-url",
        type=str,
        default=get_alertmanager_url(),
        help="AlertManager URL (default: http://localhost:9093)",
    )
    
    args = parser.parse_args()
    
    if args.list_alerts:
        list_alerts()
        return 0
    
    if not args.alert_type:
        parser.print_help()
        print("\nError: --alert-type is required (or use --list-alerts)")
        return 1
    
    # Parse custom labels
    custom_labels = {}
    if args.custom_label:
        for label in args.custom_label:
            if "=" not in label:
                print(f"Error: Invalid custom label format: {label}")
                print("Expected format: key=value")
                return 1
            key, value = label.split("=", 1)
            custom_labels[key] = value
    
    try:
        # Create and send alert
        alert_payload = create_alert_payload(
            args.alert_type,
            severity=args.severity,
            custom_labels=custom_labels,
        )
        
        success = send_alert(args.alertmanager_url, alert_payload)
        
        if not success:
            return 1
        
        # Optionally resolve alert after delay
        if args.resolve:
            print("\nWaiting 10 seconds before resolving alert...")
            time.sleep(10)
            resolve_alert(args.alertmanager_url, alert_payload)
        else:
            print("\n💡 Tip: Use --resolve to automatically resolve the alert after 10 seconds")
        
        return 0
    
    except ValueError as e:
        print(f"Error: {e}")
        print("\nUse --list-alerts to see available alert types")
        return 1
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1


if __name__ == "__main__":
    sys.exit(main())
