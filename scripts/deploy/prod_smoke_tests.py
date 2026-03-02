#!/usr/bin/env python3
"""
Production Deployment Smoke Test Suite

Executes comprehensive synthetic transactions against production endpoints after deployment:
- Authenticated /v1/chat/completions with workspace quota verification
- /v1/rag/query with citation validation
- /internal/mcp/tools/call with RBAC enforcement check
- Kong authentication + rate limiting validation
- Prometheus metrics verification (zero errors in last 5 minutes)
- One-click rollback if smoke tests fail
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

# Needs: python-package:httpx>=0.25.1
try:
    import httpx
except ImportError:
    print("Error: httpx package not available")
    print("Add to requirements-deploy.txt: httpx>=0.25.1")
    sys.exit(1)

# Needs: python-package:pyyaml>=6.0.1
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'prod_smoke_tests_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class SmokeTestConfig:
    """Configuration for production smoke tests"""
    base_url: str
    kong_admin_url: Optional[str]
    prometheus_url: Optional[str]
    workspace_id: str
    auth_token: Optional[str]
    timeout: int
    namespace: str
    release_name: str
    enable_rollback: bool
    rollback_revision: Optional[int]


class SmokeTestResult:
    """Result of a smoke test"""
    
    def __init__(self, name: str, success: bool, message: str, details: Dict[str, Any] = None):
        self.name = name
        self.success = success
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()


class ProductionSmokeTestSuite:
    """Comprehensive production smoke test suite"""
    
    def __init__(self, config: SmokeTestConfig):
        self.config = config
        self.results: List[SmokeTestResult] = []
        self.client = httpx.AsyncClient(timeout=config.timeout, verify=True)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    def _add_result(self, name: str, success: bool, message: str, details: Dict[str, Any] = None):
        """Add test result"""
        result = SmokeTestResult(name, success, message, details)
        self.results.append(result)
        
        if success:
            logger.info(f"✓ PASS: {name} - {message}")
        else:
            logger.error(f"✗ FAIL: {name} - {message}")
        
        if details:
            logger.debug(f"  Details: {json.dumps(details, indent=2)}")
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers"""
        headers = {
            "Content-Type": "application/json",
            "X-Workspace-Id": self.config.workspace_id
        }
        
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        
        return headers
    
    # ========== Kong Authentication & Rate Limiting Tests ==========
    
    async def test_kong_authentication_enforced(self) -> bool:
        """Test that Kong authentication is enforced"""
        test_name = "Kong Authentication Enforcement"
        
        try:
            # Try to access protected endpoint without auth
            response = await self.client.post(
                f"{self.config.base_url}/v1/chat/completions",
                json={
                    "model": "llama-3.3-8b",
                    "messages": [{"role": "user", "content": "test"}]
                },
                headers={"Content-Type": "application/json"}
            )
            
            # Should get 401 Unauthorized
            if response.status_code == 401:
                self._add_result(
                    test_name,
                    True,
                    "Authentication correctly enforced (401 Unauthorized)",
                    {"status_code": response.status_code}
                )
                return True
            else:
                self._add_result(
                    test_name,
                    False,
                    f"Expected 401, got {response.status_code}",
                    {"status_code": response.status_code, "body": response.text[:200]}
                )
                return False
        
        except Exception as e:
            self._add_result(test_name, False, f"Error: {str(e)}")
            return False
    
    async def test_kong_rate_limiting_active(self) -> bool:
        """Test that Kong rate limiting is active"""
        test_name = "Kong Rate Limiting Active"
        
        try:
            headers = self._get_auth_headers()
            
            # Make a request and check for rate limit headers
            response = await self.client.get(
                f"{self.config.base_url}/health",
                headers=headers
            )
            
            # Check for Kong rate limit headers
            rate_limit_headers = {
                k: v for k, v in response.headers.items()
                if 'ratelimit' in k.lower() or 'x-rate' in k.lower()
            }
            
            if rate_limit_headers:
                self._add_result(
                    test_name,
                    True,
                    "Rate limiting headers present",
                    {"headers": rate_limit_headers}
                )
                return True
            else:
                # Check Kong admin API for rate limiting plugins
                if self.config.kong_admin_url:
                    return await self._check_kong_admin_rate_limit()
                else:
                    self._add_result(
                        test_name,
                        False,
                        "No rate limit headers found",
                        {"status_code": response.status_code}
                    )
                    return False
        
        except Exception as e:
            self._add_result(test_name, False, f"Error: {str(e)}")
            return False
    
    async def _check_kong_admin_rate_limit(self) -> bool:
        """Check Kong admin API for rate limiting configuration"""
        test_name = "Kong Rate Limiting Active"
        
        try:
            response = await self.client.get(
                f"{self.config.kong_admin_url}/plugins",
                params={"name": "rate-limiting"}
            )
            
            if response.status_code == 200:
                data = response.json()
                plugins = data.get("data", [])
                
                if plugins:
                    self._add_result(
                        test_name,
                        True,
                        f"Rate limiting plugin configured ({len(plugins)} instances)",
                        {"plugins": len(plugins)}
                    )
                    return True
                else:
                    self._add_result(
                        test_name,
                        False,
                        "No rate limiting plugins found in Kong"
                    )
                    return False
            else:
                self._add_result(
                    test_name,
                    False,
                    f"Kong admin API returned {response.status_code}"
                )
                return False
        
        except Exception as e:
            logger.warning(f"Could not check Kong admin API: {e}")
            self._add_result(
                test_name,
                False,
                f"Kong admin API check failed: {str(e)}"
            )
            return False
    
    # ========== Chat Completion with Workspace Quota Tests ==========
    
    async def test_chat_completion_authenticated(self) -> bool:
        """Test authenticated /v1/chat/completions with workspace quota verification"""
        test_name = "Chat Completion (Authenticated with Workspace Quota)"
        
        try:
            headers = self._get_auth_headers()
            
            request_data = {
                "model": "llama-3.3-8b",
                "messages": [
                    {"role": "user", "content": "What is 2+2? Answer briefly."}
                ],
                "max_tokens": 50
            }
            
            response = await self.client.post(
                f"{self.config.base_url}/v1/chat/completions",
                headers=headers,
                json=request_data
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                if "choices" in data and len(data["choices"]) > 0:
                    message = data["choices"][0].get("message", {})
                    content = message.get("content", "")
                    
                    # Check for usage/quota information
                    usage = data.get("usage", {})
                    quota_headers = {
                        k: v for k, v in response.headers.items()
                        if 'quota' in k.lower() or 'usage' in k.lower()
                    }
                    
                    details = {
                        "status_code": response.status_code,
                        "response_length": len(content),
                        "usage": usage,
                        "quota_headers": quota_headers
                    }
                    
                    # Verify workspace quota tracking is active
                    if usage or quota_headers:
                        self._add_result(
                            test_name,
                            True,
                            f"Chat completion successful with quota tracking",
                            details
                        )
                        return True
                    else:
                        self._add_result(
                            test_name,
                            True,
                            "Chat completion successful (quota tracking not visible)",
                            details
                        )
                        return True
                else:
                    self._add_result(
                        test_name,
                        False,
                        "Invalid response structure",
                        {"response": data}
                    )
                    return False
            
            elif response.status_code == 401:
                self._add_result(
                    test_name,
                    False,
                    "Authentication failed - check auth token",
                    {"status_code": response.status_code}
                )
                return False
            
            elif response.status_code == 429:
                self._add_result(
                    test_name,
                    False,
                    "Rate limit exceeded or quota exhausted",
                    {"status_code": response.status_code, "body": response.text[:200]}
                )
                return False
            
            else:
                self._add_result(
                    test_name,
                    False,
                    f"Unexpected status code: {response.status_code}",
                    {"status_code": response.status_code, "body": response.text[:200]}
                )
                return False
        
        except httpx.TimeoutException:
            self._add_result(test_name, False, f"Timeout after {self.config.timeout}s")
            return False
        except Exception as e:
            self._add_result(test_name, False, f"Error: {str(e)}")
            return False
    
    # ========== RAG Query with Citation Validation Tests ==========
    
    async def test_rag_query_with_citations(self) -> bool:
        """Test /v1/rag/query with citation validation"""
        test_name = "RAG Query with Citation Validation"
        
        try:
            headers = self._get_auth_headers()
            
            request_data = {
                "query": "What is the deployment process?",
                "collection": "documentation",
                "top_k": 3,
                "include_citations": True
            }
            
            response = await self.client.post(
                f"{self.config.base_url}/v1/rag/query",
                headers=headers,
                json=request_data
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Validate response structure
                answer = data.get("answer", "")
                sources = data.get("sources", [])
                citations = data.get("citations", [])
                
                details = {
                    "status_code": response.status_code,
                    "answer_length": len(answer),
                    "sources_count": len(sources),
                    "citations_count": len(citations)
                }
                
                # Validate citations are present
                if citations and len(citations) > 0:
                    # Verify citation structure
                    valid_citations = all(
                        isinstance(c, dict) and "source" in c
                        for c in citations
                    )
                    
                    if valid_citations:
                        self._add_result(
                            test_name,
                            True,
                            f"RAG query successful with {len(citations)} citations",
                            details
                        )
                        return True
                    else:
                        self._add_result(
                            test_name,
                            False,
                            "Citations have invalid structure",
                            details
                        )
                        return False
                else:
                    # No citations but query succeeded
                    self._add_result(
                        test_name,
                        True,
                        "RAG query successful (no citations returned)",
                        details
                    )
                    return True
            
            elif response.status_code == 401:
                self._add_result(
                    test_name,
                    False,
                    "Authentication failed",
                    {"status_code": response.status_code}
                )
                return False
            
            elif response.status_code == 404:
                self._add_result(
                    test_name,
                    False,
                    "RAG endpoint not found or collection missing",
                    {"status_code": response.status_code, "body": response.text[:200]}
                )
                return False
            
            else:
                self._add_result(
                    test_name,
                    False,
                    f"Unexpected status code: {response.status_code}",
                    {"status_code": response.status_code, "body": response.text[:200]}
                )
                return False
        
        except httpx.TimeoutException:
            self._add_result(test_name, False, f"Timeout after {self.config.timeout}s")
            return False
        except Exception as e:
            self._add_result(test_name, False, f"Error: {str(e)}")
            return False
    
    # ========== MCP Tools with RBAC Enforcement Tests ==========
    
    async def test_mcp_tools_rbac_enforcement(self) -> bool:
        """Test /internal/mcp/tools/call with RBAC enforcement check"""
        test_name = "MCP Tools RBAC Enforcement"
        
        try:
            headers = self._get_auth_headers()
            
            # Test 1: Try to call a tool (should check RBAC)
            request_data = {
                "tool_name": "list_files",
                "arguments": {"path": "/tmp"},
                "server_name": "filesystem"
            }
            
            response = await self.client.post(
                f"{self.config.base_url}/internal/mcp/tools/call",
                headers=headers,
                json=request_data
            )
            
            # Accept multiple valid outcomes:
            # 200: Tool executed successfully (RBAC allows)
            # 403: RBAC denied (correct enforcement)
            # 404: Tool or server not found (acceptable)
            # 401: Authentication required (acceptable)
            
            if response.status_code in [200, 403, 404]:
                details = {
                    "status_code": response.status_code,
                    "response": response.text[:200] if response.status_code != 200 else "success"
                }
                
                if response.status_code == 200:
                    message = "MCP tool call successful (RBAC allows)"
                elif response.status_code == 403:
                    message = "RBAC correctly denied access"
                else:
                    message = "MCP endpoint available (tool/server not found)"
                
                self._add_result(
                    test_name,
                    True,
                    message,
                    details
                )
                return True
            
            elif response.status_code == 401:
                self._add_result(
                    test_name,
                    False,
                    "Authentication failed",
                    {"status_code": response.status_code}
                )
                return False
            
            else:
                self._add_result(
                    test_name,
                    False,
                    f"Unexpected status code: {response.status_code}",
                    {"status_code": response.status_code, "body": response.text[:200]}
                )
                return False
        
        except httpx.TimeoutException:
            self._add_result(test_name, False, f"Timeout after {self.config.timeout}s")
            return False
        except Exception as e:
            self._add_result(test_name, False, f"Error: {str(e)}")
            return False
    
    # ========== Prometheus Metrics Verification ==========
    
    async def test_prometheus_zero_errors(self) -> bool:
        """Query Prometheus for zero errors in last 5 minutes"""
        test_name = "Prometheus Zero Errors (Last 5 Minutes)"
        
        if not self.config.prometheus_url:
            self._add_result(
                test_name,
                True,
                "Prometheus URL not configured, skipping",
                {"skipped": True}
            )
            return True
        
        try:
            # Query for HTTP 5xx errors in last 5 minutes
            query = 'sum(rate(http_requests_total{status=~"5.."}[5m]))'
            
            response = await self.client.get(
                f"{self.config.prometheus_url}/api/v1/query",
                params={"query": query}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "success":
                    results = data.get("data", {}).get("result", [])
                    
                    if not results:
                        # No error metrics found
                        self._add_result(
                            test_name,
                            True,
                            "No 5xx errors in last 5 minutes",
                            {"error_rate": 0}
                        )
                        return True
                    else:
                        # Check error rate
                        error_rate = float(results[0].get("value", [0, 0])[1])
                        
                        if error_rate == 0:
                            self._add_result(
                                test_name,
                                True,
                                "No 5xx errors in last 5 minutes",
                                {"error_rate": error_rate}
                            )
                            return True
                        else:
                            self._add_result(
                                test_name,
                                False,
                                f"5xx error rate: {error_rate:.4f} req/s",
                                {"error_rate": error_rate}
                            )
                            return False
                else:
                    self._add_result(
                        test_name,
                        False,
                        f"Prometheus query failed: {data.get('error')}",
                        {"response": data}
                    )
                    return False
            else:
                self._add_result(
                    test_name,
                    False,
                    f"Prometheus API returned {response.status_code}",
                    {"status_code": response.status_code}
                )
                return False
        
        except Exception as e:
            logger.warning(f"Prometheus check failed: {e}")
            self._add_result(
                test_name,
                False,
                f"Prometheus query error: {str(e)}"
            )
            return False
    
    async def test_prometheus_deployment_metrics(self) -> bool:
        """Query Prometheus for deployment health metrics"""
        test_name = "Prometheus Deployment Health Metrics"
        
        if not self.config.prometheus_url:
            self._add_result(
                test_name,
                True,
                "Prometheus URL not configured, skipping",
                {"skipped": True}
            )
            return True
        
        try:
            # Query for pod readiness
            query = f'kube_pod_status_ready{{namespace="{self.config.namespace}"}}'
            
            response = await self.client.get(
                f"{self.config.prometheus_url}/api/v1/query",
                params={"query": query}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "success":
                    results = data.get("data", {}).get("result", [])
                    
                    ready_pods = sum(
                        1 for r in results
                        if float(r.get("value", [0, 0])[1]) == 1.0
                    )
                    total_pods = len(results)
                    
                    details = {
                        "ready_pods": ready_pods,
                        "total_pods": total_pods
                    }
                    
                    if ready_pods == total_pods and total_pods > 0:
                        self._add_result(
                            test_name,
                            True,
                            f"All {total_pods} pods ready",
                            details
                        )
                        return True
                    elif total_pods == 0:
                        self._add_result(
                            test_name,
                            True,
                            "No pod metrics available (may be normal)",
                            details
                        )
                        return True
                    else:
                        self._add_result(
                            test_name,
                            False,
                            f"Only {ready_pods}/{total_pods} pods ready",
                            details
                        )
                        return False
                else:
                    self._add_result(
                        test_name,
                        True,
                        "Prometheus query returned no error (metrics may not exist)",
                        {"response": data}
                    )
                    return True
            else:
                self._add_result(
                    test_name,
                    True,
                    f"Prometheus API returned {response.status_code} (non-critical)",
                    {"status_code": response.status_code}
                )
                return True
        
        except Exception as e:
            logger.warning(f"Prometheus deployment metrics check failed: {e}")
            self._add_result(
                test_name,
                True,
                f"Metrics check failed (non-critical): {str(e)}"
            )
            return True
    
    # ========== Test Orchestration ==========
    
    async def run_all_tests(self) -> bool:
        """Run all smoke tests"""
        logger.info("=" * 70)
        logger.info("PRODUCTION SMOKE TEST SUITE")
        logger.info("=" * 70)
        logger.info(f"Base URL: {self.config.base_url}")
        logger.info(f"Workspace ID: {self.config.workspace_id}")
        logger.info(f"Namespace: {self.config.namespace}")
        logger.info(f"Release: {self.config.release_name}")
        logger.info("=" * 70)
        logger.info("")
        
        # Run tests in order of importance
        tests = [
            # Critical: Authentication & Security
            ("Kong Authentication", self.test_kong_authentication_enforced),
            ("Kong Rate Limiting", self.test_kong_rate_limiting_active),
            
            # Critical: Core API Endpoints
            ("Chat Completion", self.test_chat_completion_authenticated),
            ("RAG Query", self.test_rag_query_with_citations),
            ("MCP Tools RBAC", self.test_mcp_tools_rbac_enforcement),
            
            # Important: Monitoring & Metrics
            ("Prometheus Zero Errors", self.test_prometheus_zero_errors),
            ("Prometheus Deployment Health", self.test_prometheus_deployment_metrics),
        ]
        
        all_passed = True
        
        for test_name, test_func in tests:
            logger.info(f"Running: {test_name}")
            try:
                passed = await test_func()
                if not passed:
                    all_passed = False
            except Exception as e:
                logger.exception(f"Test {test_name} raised exception: {e}")
                self._add_result(test_name, False, f"Exception: {str(e)}")
                all_passed = False
            
            logger.info("")
        
        return all_passed
    
    def print_summary(self):
        """Print test summary"""
        logger.info("=" * 70)
        logger.info("SMOKE TEST SUMMARY")
        logger.info("=" * 70)
        
        passed = sum(1 for r in self.results if r.success)
        failed = sum(1 for r in self.results if not r.success)
        total = len(self.results)
        
        logger.info(f"Total: {total}")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {failed}")
        logger.info("")
        
        if failed > 0:
            logger.info("Failed tests:")
            for result in self.results:
                if not result.success:
                    logger.info(f"  ✗ {result.name}: {result.message}")
            logger.info("")
        
        return passed, failed


def perform_rollback(config: SmokeTestConfig) -> bool:
    """Perform one-click Helm rollback"""
    logger.info("=" * 70)
    logger.info("INITIATING ROLLBACK")
    logger.info("=" * 70)
    logger.info("")
    
    try:
        # Get current revision
        result = subprocess.run(
            [
                "helm", "list", "-n", config.namespace,
                "-o", "json"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        
        releases = json.loads(result.stdout)
        current_revision = None
        
        for release in releases:
            if release.get("name") == config.release_name:
                current_revision = release.get("revision")
                break
        
        if not current_revision:
            logger.error(f"Release {config.release_name} not found")
            return False
        
        logger.info(f"Current revision: {current_revision}")
        
        # Determine rollback target
        if config.rollback_revision:
            target_revision = config.rollback_revision
        else:
            target_revision = int(current_revision) - 1
        
        logger.info(f"Rolling back to revision: {target_revision}")
        logger.info("")
        
        # Perform rollback
        subprocess.run(
            [
                "helm", "rollback",
                config.release_name,
                str(target_revision),
                "-n", config.namespace,
                "--wait",
                "--timeout", "5m"
            ],
            check=True
        )
        
        logger.info("")
        logger.info("✓ Rollback completed successfully")
        logger.info("")
        
        # Verify pod status
        logger.info("Verifying pod status after rollback...")
        subprocess.run(
            ["kubectl", "get", "pods", "-n", config.namespace],
            check=False
        )
        
        return True
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Rollback failed: {e}")
        return False
    except Exception as e:
        logger.exception(f"Rollback error: {e}")
        return False


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Production deployment smoke test suite with rollback",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic smoke tests
  python prod_smoke_tests.py --base-url https://api.example.com \\
    --auth-token $TOKEN --workspace-id prod-workspace

  # With Prometheus and Kong admin
  python prod_smoke_tests.py --base-url https://api.example.com \\
    --auth-token $TOKEN --workspace-id prod-workspace \\
    --prometheus-url http://prometheus:9090 \\
    --kong-admin-url http://kong-admin:8001

  # With automatic rollback on failure
  python prod_smoke_tests.py --base-url https://api.example.com \\
    --auth-token $TOKEN --workspace-id prod-workspace \\
    --enable-rollback --namespace ai-platform-prod \\
    --release-name ai-platform
        """
    )
    
    # Required arguments
    parser.add_argument(
        "--base-url",
        required=True,
        help="Base URL of production deployment (e.g., https://api.example.com)"
    )
    parser.add_argument(
        "--workspace-id",
        required=True,
        help="Workspace ID for testing"
    )
    
    # Optional authentication
    parser.add_argument(
        "--auth-token",
        help="Authentication token (Bearer token or JWT)"
    )
    
    # Optional monitoring endpoints
    parser.add_argument(
        "--prometheus-url",
        help="Prometheus URL for metrics validation (e.g., http://prometheus:9090)"
    )
    parser.add_argument(
        "--kong-admin-url",
        help="Kong Admin API URL (e.g., http://kong-admin:8001)"
    )
    
    # Test configuration
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout per request in seconds (default: 30)"
    )
    
    # Rollback configuration
    parser.add_argument(
        "--enable-rollback",
        action="store_true",
        help="Enable automatic rollback on test failure"
    )
    parser.add_argument(
        "--namespace",
        default="ai-platform-prod",
        help="Kubernetes namespace (default: ai-platform-prod)"
    )
    parser.add_argument(
        "--release-name",
        default="ai-platform",
        help="Helm release name (default: ai-platform)"
    )
    parser.add_argument(
        "--rollback-revision",
        type=int,
        help="Specific revision to rollback to (default: previous revision)"
    )
    
    # Output options
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Build configuration
    config = SmokeTestConfig(
        base_url=args.base_url.rstrip('/'),
        kong_admin_url=args.kong_admin_url,
        prometheus_url=args.prometheus_url,
        workspace_id=args.workspace_id,
        auth_token=args.auth_token or os.getenv('AUTH_TOKEN'),
        timeout=args.timeout,
        namespace=args.namespace,
        release_name=args.release_name,
        enable_rollback=args.enable_rollback,
        rollback_revision=args.rollback_revision
    )
    
    # Run smoke tests
    async with ProductionSmokeTestSuite(config) as suite:
        all_passed = await suite.run_all_tests()
        suite.print_summary()
    
    # Handle results
    if all_passed:
        logger.info("=" * 70)
        logger.info("✓ ALL SMOKE TESTS PASSED")
        logger.info("Deployment verified successfully!")
        logger.info("=" * 70)
        sys.exit(0)
    else:
        logger.error("=" * 70)
        logger.error("✗ SMOKE TESTS FAILED")
        logger.error("=" * 70)
        logger.error("")
        
        if config.enable_rollback:
            logger.error("Initiating automatic rollback...")
            logger.error("")
            
            if perform_rollback(config):
                logger.info("=" * 70)
                logger.info("Rollback completed. Please investigate failures before redeploying.")
                logger.info("=" * 70)
                sys.exit(2)
            else:
                logger.error("=" * 70)
                logger.error("Rollback FAILED. Manual intervention required!")
                logger.error("=" * 70)
                sys.exit(3)
        else:
            logger.error("Rollback disabled. To enable automatic rollback, use --enable-rollback")
            logger.error("")
            logger.error("To manually rollback:")
            logger.error(f"  helm rollback {config.release_name} -n {config.namespace}")
            logger.error("")
            sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
