#!/usr/bin/env python3
"""
Test script for Drift Monitor Service
"""

import httpx
import asyncio
import json
from datetime import datetime


async def test_drift_monitor():
    """Test drift monitor endpoints"""
    base_url = "http://localhost:8004"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("=" * 60)
        print("Testing Drift Monitor Service")
        print("=" * 60)
        
        # 1. Health check
        print("\n1. Testing health check...")
        try:
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("✓ Health check passed")
                data = response.json()
                print(f"  Status: {data['status']}")
                print(f"  Version: {data['version']}")
                print(f"  Monitoring: {data['is_monitoring']}")
                print(f"  Config: {json.dumps(data['config'], indent=2)}")
            else:
                print(f"✗ Health check failed: {response.status_code}")
        except Exception as e:
            print(f"✗ Health check error: {e}")
        
        # 2. Manual drift check
        print("\n2. Testing manual drift check...")
        try:
            response = await client.post(f"{base_url}/drift/check")
            if response.status_code == 200:
                print("✓ Drift check completed")
                data = response.json()
                print(f"  Status: {data['status']}")
                print(f"  Drift Detected: {data['drift_detected']}")
                print(f"  Severity: {data.get('severity', 'N/A')}")
                if data.get('metrics'):
                    print("  Metrics:")
                    for key, value in data['metrics'].items():
                        if isinstance(value, float):
                            print(f"    {key}: {value:.4f}")
                        else:
                            print(f"    {key}: {value}")
            else:
                print(f"✗ Drift check failed: {response.status_code}")
                print(f"  Response: {response.text}")
        except Exception as e:
            print(f"✗ Drift check error: {e}")
        
        # 3. Get drift metrics
        print("\n3. Testing drift metrics retrieval...")
        try:
            response = await client.get(f"{base_url}/drift/metrics?days=30")
            if response.status_code == 200:
                print("✓ Drift metrics retrieved")
                data = response.json()
                print(f"  Total metrics: {data['total']}")
                print(f"  Days: {data['days']}")
                if data['metrics']:
                    print(f"  Latest metrics:")
                    latest = data['metrics'][0]
                    print(f"    KL Divergence: {latest['kl_divergence']:.4f}")
                    print(f"    PSI: {latest['psi']:.4f}")
                    print(f"    Drift Detected: {latest['drift_detected']}")
                    print(f"    Severity: {latest.get('severity', 'N/A')}")
            else:
                print(f"✗ Failed to get metrics: {response.status_code}")
        except Exception as e:
            print(f"✗ Metrics retrieval error: {e}")
        
        # 4. Get drift summary
        print("\n4. Testing drift summary...")
        try:
            response = await client.get(f"{base_url}/drift/summary")
            if response.status_code == 200:
                print("✓ Drift summary retrieved")
                data = response.json()
                print(f"  Summary:")
                summary = data.get('summary', {})
                print(f"    Total checks: {summary.get('total_checks', 0)}")
                print(f"    Drift count: {summary.get('drift_count', 0)}")
                print(f"    Critical: {summary.get('critical_count', 0)}")
                print(f"    Warning: {summary.get('warning_count', 0)}")
                print(f"    Avg KL: {summary.get('avg_kl', 0):.4f}")
                print(f"    Avg PSI: {summary.get('avg_psi', 0):.4f}")
                print(f"  Fine-tuning triggers: {data.get('finetuning_triggers', 0)}")
                print(f"  Is monitoring: {data.get('is_monitoring', False)}")
            else:
                print(f"✗ Failed to get summary: {response.status_code}")
        except Exception as e:
            print(f"✗ Summary retrieval error: {e}")
        
        # 5. Test custom window drift check
        print("\n5. Testing custom window drift check...")
        try:
            payload = {"window_days": 14}
            response = await client.post(
                f"{base_url}/drift/check",
                json=payload
            )
            if response.status_code == 200:
                print("✓ Custom window drift check completed")
                data = response.json()
                print(f"  Status: {data['status']}")
                print(f"  Drift Detected: {data['drift_detected']}")
            else:
                print(f"✗ Custom drift check failed: {response.status_code}")
                print(f"  Response: {response.text}")
        except Exception as e:
            print(f"✗ Custom drift check error: {e}")
        
        print("\n" + "=" * 60)
        print("Drift Monitor Tests Complete")
        print("=" * 60)


def main():
    """Run tests"""
    print(f"Starting Drift Monitor tests at {datetime.now()}")
    asyncio.run(test_drift_monitor())


if __name__ == "__main__":
    main()
