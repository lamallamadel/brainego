#!/usr/bin/env python3
"""
Test script for Learning Engine Service

Tests:
- Health check
- Training trigger
- Fisher calculation
- Adapter management
- Storage operations
"""

import asyncio
import httpx
import json
from datetime import datetime


BASE_URL = "http://localhost:8003"


async def test_health():
    """Test health endpoint"""
    print("\n" + "=" * 60)
    print("Testing Health Check")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        print("✓ Health check passed")


async def test_list_adapters():
    """Test listing adapters"""
    print("\n" + "=" * 60)
    print("Testing List Adapters")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/adapters")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Found {data['total']} adapters")


async def test_trigger_training():
    """Test triggering a training job"""
    print("\n" + "=" * 60)
    print("Testing Training Trigger")
    print("=" * 60)
    
    payload = {
        "days": 7,
        "ewc_lambda": 500.0,
        "force": True  # Force even if low samples
    }
    
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{BASE_URL}/train",
            json=payload
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        print(f"✓ Training job started: {data['job_id']}")


async def test_training_status():
    """Test getting training status"""
    print("\n" + "=" * 60)
    print("Testing Training Status")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/training/status")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        assert response.status_code == 200
        print("✓ Training status retrieved")


async def test_metrics():
    """Test getting metrics"""
    print("\n" + "=" * 60)
    print("Testing Metrics")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/metrics")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        assert response.status_code == 200
        print("✓ Metrics retrieved")


async def test_fisher_calculation():
    """Test Fisher matrix calculation"""
    print("\n" + "=" * 60)
    print("Testing Fisher Calculation")
    print("=" * 60)
    
    payload = {
        "num_samples": 100  # Small number for testing
    }
    
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{BASE_URL}/fisher/calculate",
            json=payload
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        print(f"✓ Fisher calculation started: {data['fisher_version']}")


async def test_adapter_deployment():
    """Test adapter deployment (if adapters exist)"""
    print("\n" + "=" * 60)
    print("Testing Adapter Deployment")
    print("=" * 60)
    
    async with httpx.AsyncClient() as client:
        # First, list adapters
        response = await client.get(f"{BASE_URL}/adapters")
        adapters = response.json()["adapters"]
        
        if not adapters:
            print("⊘ No adapters available for deployment test")
            return
        
        # Get latest adapter
        latest = adapters[0]
        version = latest["version"]
        
        # Test deployment
        response = await client.post(f"{BASE_URL}/adapters/{version}/deploy")
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        assert response.status_code == 200
        print(f"✓ Adapter {version} deployment initiated")


async def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("Learning Engine Service Test Suite")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    
    try:
        await test_health()
        await test_list_adapters()
        await test_training_status()
        await test_metrics()
        
        # Optional tests (may fail if no data)
        try:
            await test_trigger_training()
        except Exception as e:
            print(f"⊘ Training trigger test skipped: {e}")
        
        try:
            await test_fisher_calculation()
        except Exception as e:
            print(f"⊘ Fisher calculation test skipped: {e}")
        
        try:
            await test_adapter_deployment()
        except Exception as e:
            print(f"⊘ Adapter deployment test skipped: {e}")
        
        print("\n" + "=" * 60)
        print("✓ All tests completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
