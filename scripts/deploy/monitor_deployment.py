#!/usr/bin/env python3
"""
Deployment Status Monitor

Real-time monitoring of deployment status with detailed pod, StatefulSet,
and service health information.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional


def run_kubectl(args: List[str]) -> Optional[Dict]:
    """Execute kubectl command and return JSON output"""
    try:
        result = subprocess.run(
            ["kubectl"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        return None


def get_pod_status(namespace: str) -> Dict[str, int]:
    """Get pod status summary"""
    data = run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])
    
    if not data:
        return {}
    
    status = {
        "Running": 0,
        "Pending": 0,
        "Failed": 0,
        "Succeeded": 0,
        "Unknown": 0
    }
    
    for pod in data.get("items", []):
        phase = pod.get("status", {}).get("phase", "Unknown")
        status[phase] = status.get(phase, 0) + 1
    
    return status


def get_statefulset_status(namespace: str) -> List[Dict]:
    """Get StatefulSet status"""
    data = run_kubectl(["get", "statefulset", "-n", namespace, "-o", "json"])
    
    if not data:
        return []
    
    statefulsets = []
    
    for sts in data.get("items", []):
        name = sts["metadata"]["name"]
        spec = sts.get("spec", {})
        status = sts.get("status", {})
        
        statefulsets.append({
            "name": name,
            "desired": spec.get("replicas", 0),
            "ready": status.get("readyReplicas", 0),
            "current": status.get("currentReplicas", 0),
            "updated": status.get("updatedReplicas", 0)
        })
    
    return statefulsets


def get_pvc_status(namespace: str) -> List[Dict]:
    """Get PVC status"""
    data = run_kubectl(["get", "pvc", "-n", namespace, "-o", "json"])
    
    if not data:
        return []
    
    pvcs = []
    
    for pvc in data.get("items", []):
        name = pvc["metadata"]["name"]
        status = pvc.get("status", {})
        spec = pvc.get("spec", {})
        
        pvcs.append({
            "name": name,
            "phase": status.get("phase", "Unknown"),
            "size": spec.get("resources", {}).get("requests", {}).get("storage", "Unknown")
        })
    
    return pvcs


def get_service_status(namespace: str) -> List[Dict]:
    """Get Service status"""
    data = run_kubectl(["get", "service", "-n", namespace, "-o", "json"])
    
    if not data:
        return []
    
    services = []
    
    for svc in data.get("items", []):
        name = svc["metadata"]["name"]
        spec = svc.get("spec", {})
        
        services.append({
            "name": name,
            "type": spec.get("type", "Unknown"),
            "cluster_ip": spec.get("clusterIP", "None"),
            "ports": len(spec.get("ports", []))
        })
    
    return services


def get_ingress_status(namespace: str) -> List[Dict]:
    """Get Ingress status"""
    data = run_kubectl(["get", "ingress", "-n", namespace, "-o", "json"])
    
    if not data:
        return []
    
    ingresses = []
    
    for ing in data.get("items", []):
        name = ing["metadata"]["name"]
        spec = ing.get("spec", {})
        status = ing.get("status", {})
        
        hosts = []
        for rule in spec.get("rules", []):
            if "host" in rule:
                hosts.append(rule["host"])
        
        ingresses.append({
            "name": name,
            "hosts": hosts,
            "tls": len(spec.get("tls", []))
        })
    
    return ingresses


def display_status(namespace: str, watch: bool = False, interval: int = 5):
    """Display deployment status"""
    
    while True:
        # Clear screen on watch mode
        if watch:
            print("\033[2J\033[H")  # Clear screen and move cursor to top
        
        print("=" * 80)
        print(f"DEPLOYMENT STATUS - {namespace}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        print()
        
        # Pod Status
        print("POD STATUS")
        print("-" * 40)
        pod_status = get_pod_status(namespace)
        if pod_status:
            total = sum(pod_status.values())
            for phase, count in pod_status.items():
                if count > 0:
                    percentage = (count / total * 100) if total > 0 else 0
                    marker = "✓" if phase == "Running" else "✗" if phase == "Failed" else "○"
                    print(f"  {marker} {phase:12} : {count:3d} ({percentage:5.1f}%)")
        else:
            print("  No pods found")
        print()
        
        # StatefulSet Status
        print("STATEFULSET STATUS")
        print("-" * 40)
        statefulsets = get_statefulset_status(namespace)
        if statefulsets:
            for sts in statefulsets:
                name = sts["name"]
                desired = sts["desired"]
                ready = sts["ready"]
                marker = "✓" if ready == desired else "⚠"
                print(f"  {marker} {name:20} : {ready}/{desired} ready")
        else:
            print("  No StatefulSets found")
        print()
        
        # PVC Status
        print("PVC STATUS")
        print("-" * 40)
        pvcs = get_pvc_status(namespace)
        if pvcs:
            for pvc in pvcs:
                name = pvc["name"]
                phase = pvc["phase"]
                size = pvc["size"]
                marker = "✓" if phase == "Bound" else "✗"
                print(f"  {marker} {name:30} : {phase:10} ({size})")
        else:
            print("  No PVCs found")
        print()
        
        # Service Status
        print("SERVICE STATUS")
        print("-" * 40)
        services = get_service_status(namespace)
        if services:
            for svc in services:
                name = svc["name"]
                svc_type = svc["type"]
                cluster_ip = svc["cluster_ip"]
                ports = svc["ports"]
                print(f"  ✓ {name:20} : {svc_type:15} ({cluster_ip}, {ports} port(s))")
        else:
            print("  No Services found")
        print()
        
        # Ingress Status
        print("INGRESS STATUS")
        print("-" * 40)
        ingresses = get_ingress_status(namespace)
        if ingresses:
            for ing in ingresses:
                name = ing["name"]
                hosts = ", ".join(ing["hosts"]) if ing["hosts"] else "No hosts"
                tls = ing["tls"]
                tls_marker = "🔒" if tls > 0 else "○"
                print(f"  {tls_marker} {name:20} : {hosts}")
        else:
            print("  No Ingresses found")
        print()
        
        if not watch:
            break
        
        print(f"Refreshing in {interval}s... (Press Ctrl+C to stop)")
        time.sleep(interval)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Monitor deployment status in real-time"
    )
    
    parser.add_argument(
        "--namespace",
        default="ai-platform-prod",
        help="Kubernetes namespace to monitor (default: ai-platform-prod)"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode - continuously refresh status"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Refresh interval in seconds for watch mode (default: 5)"
    )
    
    args = parser.parse_args()
    
    try:
        display_status(args.namespace, args.watch, args.interval)
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
