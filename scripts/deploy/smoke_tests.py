#!/usr/bin/env python3
"""
Smoke Tests for Production Deployment

Tests critical endpoints after deployment to verify basic functionality.
"""

import argparse
import sys
import time
from typing import Dict, List, Tuple

# Needs: python-package:requests>=2.31.0
try:
    import requests
except ImportError:
    print("Error: requests package not available")
    print("Install with: pip install requests>=2.31.0")
    sys.exit(1)


class SmokeTest:
    """Smoke test for a production endpoint"""
    
    def __init__(self, name: str, url: str, method: str = "GET", 
                 expected_status: int = 200, timeout: int = 30,
                 headers: Dict[str, str] = None, data: Dict = None):
        self.name = name
        self.url = url
        self.method = method
        self.expected_status = expected_status
        self.timeout = timeout
        self.headers = headers or {}
        self.data = data
    
    def run(self) -> Tuple[bool, str]:
        """Execute the smoke test"""
        try:
            if self.method.upper() == "GET":
                response = requests.get(
                    self.url,
                    headers=self.headers,
                    timeout=self.timeout,
                    verify=True
                )
            elif self.method.upper() == "POST":
                response = requests.post(
                    self.url,
                    headers=self.headers,
                    json=self.data,
                    timeout=self.timeout,
                    verify=True
                )
            else:
                return False, f"Unsupported method: {self.method}"
            
            if response.status_code == self.expected_status:
                return True, f"Status: {response.status_code}"
            else:
                return False, f"Status: {response.status_code} (expected {self.expected_status})"
        
        except requests.exceptions.Timeout:
            return False, f"Timeout after {self.timeout}s"
        except requests.exceptions.SSLError as e:
            return False, f"SSL Error: {e}"
        except requests.exceptions.ConnectionError as e:
            return False, f"Connection Error: {e}"
        except Exception as e:
            return False, f"Error: {e}"


def define_production_smoke_tests(base_url: str) -> List[SmokeTest]:
    """Define production smoke tests"""
    
    return [
        # Health checks
        SmokeTest(
            name="Gateway Health Check",
            url=f"{base_url}/gateway/health"
        ),
        SmokeTest(
            name="Agent Router Health Check",
            url=f"{base_url}/v1/health"
        ),
        SmokeTest(
            name="Memory Service Health Check",
            url=f"{base_url}/memory/health"
        ),
        SmokeTest(
            name="Learning Engine Health Check",
            url=f"{base_url}/learning/health"
        ),
        SmokeTest(
            name="MCP Gateway Health Check",
            url=f"{base_url}/mcp/health"
        ),
        
        # Metrics endpoints
        SmokeTest(
            name="Prometheus Metrics",
            url=f"{base_url}/metrics"
        ),
        
        # API endpoints (basic validation)
        SmokeTest(
            name="Chat Completions Endpoint",
            url=f"{base_url}/v1/chat/completions",
            method="POST",
            expected_status=401,  # Expect unauthorized without auth
            data={
                "model": "llama-3.3-8b",
                "messages": [{"role": "user", "content": "test"}]
            }
        ),
        SmokeTest(
            name="Embeddings Endpoint",
            url=f"{base_url}/v1/embeddings",
            method="POST",
            expected_status=401,  # Expect unauthorized without auth
            data={
                "model": "llama-3.3-8b",
                "input": "test"
            }
        ),
    ]


def run_smoke_tests(tests: List[SmokeTest], retry_count: int = 3, 
                    retry_delay: int = 10) -> Tuple[int, int]:
    """Run all smoke tests with retries"""
    
    passed = 0
    failed = 0
    
    print("=" * 70)
    print("SMOKE TESTS")
    print("=" * 70)
    print()
    
    for test in tests:
        print(f"Running: {test.name}")
        print(f"  URL: {test.url}")
        
        success = False
        last_message = ""
        
        for attempt in range(retry_count):
            if attempt > 0:
                print(f"  Retry {attempt}/{retry_count - 1}...")
                time.sleep(retry_delay)
            
            success, message = test.run()
            last_message = message
            
            if success:
                break
        
        if success:
            print(f"  ✓ PASS: {last_message}")
            passed += 1
        else:
            print(f"  ✗ FAIL: {last_message}")
            failed += 1
        
        print()
    
    return passed, failed


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run smoke tests against production deployment"
    )
    
    parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL for production deployment (e.g., https://api.example.com)"
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=3,
        help="Number of retries per test (default: 3)"
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=10,
        help="Delay between retries in seconds (default: 10)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout per request in seconds (default: 30)"
    )
    
    args = parser.parse_args()
    
    # Define tests
    tests = define_production_smoke_tests(args.base_url)
    
    # Set timeout for all tests
    for test in tests:
        test.timeout = args.timeout
    
    # Run tests
    passed, failed = run_smoke_tests(
        tests,
        retry_count=args.retry_count,
        retry_delay=args.retry_delay
    )
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print()
    
    if failed == 0:
        print("✓ All smoke tests passed!")
        sys.exit(0)
    else:
        print(f"✗ {failed} smoke test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
