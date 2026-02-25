#!/usr/bin/env python3
"""
Test script for MCPJungle Gateway.

Tests MCP endpoints, authentication, authorization, and tracing.
"""

import asyncio
import httpx
import json
import sys
from typing import Dict, Any


# Configuration
BASE_URL = "http://localhost:9100"
API_KEYS = {
    "admin": "sk-admin-key-456",
    "developer": "sk-dev-key-789",
    "analyst": "sk-test-key-123",
}

# Color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{text.center(60)}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text: str):
    """Print error message."""
    print(f"{RED}✗ {text}{RESET}")


def print_info(text: str):
    """Print info message."""
    print(f"{YELLOW}ℹ {text}{RESET}")


async def test_health_check(client: httpx.AsyncClient) -> bool:
    """Test health check endpoint."""
    print_header("Testing Health Check")
    
    try:
        response = await client.get(f"{BASE_URL}/health")
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Gateway status: {data['status']}")
            
            for service, status in data['services'].items():
                if status == "healthy":
                    print_success(f"{service}: {status}")
                else:
                    print_error(f"{service}: {status}")
            
            return True
        else:
            print_error(f"Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Health check error: {e}")
        return False


async def test_authentication(client: httpx.AsyncClient) -> bool:
    """Test authentication."""
    print_header("Testing Authentication")
    
    # Test without auth
    try:
        response = await client.get(f"{BASE_URL}/mcp/servers")
        if response.status_code == 401:
            print_success("Correctly rejected request without authentication")
        else:
            print_error(f"Expected 401, got {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Auth test error: {e}")
        return False
    
    # Test with valid auth
    try:
        headers = {"Authorization": f"Bearer {API_KEYS['admin']}"}
        response = await client.get(f"{BASE_URL}/mcp/servers", headers=headers)
        
        if response.status_code == 200:
            print_success("Successfully authenticated with valid API key")
            return True
        else:
            print_error(f"Authentication failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Auth test error: {e}")
        return False


async def test_list_servers(client: httpx.AsyncClient, role: str) -> bool:
    """Test listing MCP servers."""
    print_header(f"Testing MCP Server List (Role: {role})")
    
    try:
        headers = {"Authorization": f"Bearer {API_KEYS[role]}"}
        response = await client.get(f"{BASE_URL}/mcp/servers", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Retrieved {data['total']} servers")
            print_info(f"User role: {data['role']}")
            
            for server in data['servers']:
                status = "✓" if server['connected'] else "✗"
                print(f"  {status} {server['name']} ({server['id']})")
                print(f"    Capabilities: {', '.join(server['capabilities'])}")
            
            return True
        else:
            print_error(f"Failed to list servers: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"List servers error: {e}")
        return False


async def test_role_info(client: httpx.AsyncClient, role: str) -> bool:
    """Test ACL role information."""
    print_header(f"Testing ACL Role Info (Role: {role})")
    
    try:
        headers = {"Authorization": f"Bearer {API_KEYS[role]}"}
        response = await client.get(f"{BASE_URL}/mcp/acl/role", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Role: {data['role']}")
            print_info(f"Description: {data['description']}")
            print_info(f"Available servers: {', '.join(data['servers'])}")
            
            rate_limits = data['rate_limits']
            print_info(f"Rate limits: {rate_limits['requests_per_minute']}/min, "
                      f"{rate_limits['requests_per_hour']}/hour")
            
            print("\nPermissions:")
            for server_id, perms in data['permissions'].items():
                print(f"  {server_id}:")
                print(f"    Operations: {', '.join(perms['operations'])}")
                print(f"    Resources: {perms['resources_count']}")
                print(f"    Tools: {perms['tools_count']}")
            
            return True
        else:
            print_error(f"Failed to get role info: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Role info error: {e}")
        return False


async def test_list_tools(
    client: httpx.AsyncClient, 
    role: str, 
    server_id: str
) -> bool:
    """Test listing tools from an MCP server."""
    print_header(f"Testing Tool List: {server_id} (Role: {role})")
    
    try:
        headers = {"Authorization": f"Bearer {API_KEYS[role]}"}
        payload = {"server_id": server_id}
        
        response = await client.post(
            f"{BASE_URL}/mcp/tools/list",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Retrieved {data['count']} tools")
            
            for tool in data['tools'][:5]:  # Show first 5 tools
                print(f"  • {tool['name']}")
                if tool.get('description'):
                    print(f"    {tool['description'][:60]}...")
            
            if data['count'] > 5:
                print(f"  ... and {data['count'] - 5} more tools")
            
            return True
        elif response.status_code == 403:
            print_error(f"Permission denied: {response.json()['detail']}")
            return False
        else:
            print_error(f"Failed to list tools: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"List tools error: {e}")
        return False


async def test_authorization(client: httpx.AsyncClient) -> bool:
    """Test role-based authorization."""
    print_header("Testing Authorization (Role Permissions)")
    
    # Test: analyst (read-only) trying to use write operation
    try:
        headers = {"Authorization": f"Bearer {API_KEYS['analyst']}"}
        payload = {
            "server_id": "mcp-github",
            "tool_name": "github_create_issue",
            "arguments": {"title": "Test", "body": "Test"}
        }
        
        response = await client.post(
            f"{BASE_URL}/mcp/tools/call",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 403:
            print_success("Correctly blocked analyst from write operation")
        else:
            print_error(f"Expected 403, got {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Authorization test error: {e}")
        return False
    
    # Test: developer with proper permissions
    try:
        headers = {"Authorization": f"Bearer {API_KEYS['developer']}"}
        payload = {"server_id": "mcp-github"}
        
        response = await client.post(
            f"{BASE_URL}/mcp/tools/list",
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            print_success("Developer successfully accessed allowed server")
            return True
        else:
            print_error(f"Developer access failed: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Authorization test error: {e}")
        return False


async def test_metrics(client: httpx.AsyncClient) -> bool:
    """Test metrics endpoint."""
    print_header("Testing Metrics")
    
    try:
        headers = {"Authorization": f"Bearer {API_KEYS['admin']}"}
        response = await client.get(f"{BASE_URL}/metrics", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            metrics = data['metrics']
            
            print_success("Metrics retrieved successfully")
            print_info(f"Total requests: {metrics['request_count']}")
            print_info(f"MCP requests: {metrics['mcp_requests']}")
            print_info(f"Errors: {metrics['errors']}")
            print_info(f"Auth failures: {metrics['auth_failures']}")
            print_info(f"Average latency: {metrics['avg_latency_ms']}ms")
            print_info(f"P95 latency: {metrics['p95_latency_ms']}ms")
            
            return True
        else:
            print_error(f"Failed to get metrics: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Metrics error: {e}")
        return False


async def run_all_tests():
    """Run all tests."""
    print(f"\n{BLUE}{'=' * 60}")
    print("MCPJungle Gateway Test Suite".center(60))
    print(f"{'=' * 60}{RESET}\n")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        results = []
        
        # Basic tests
        results.append(("Health Check", await test_health_check(client)))
        results.append(("Authentication", await test_authentication(client)))
        
        # Role-based tests
        for role in ["admin", "developer", "analyst"]:
            results.append(
                (f"List Servers ({role})", await test_list_servers(client, role))
            )
            results.append(
                (f"Role Info ({role})", await test_role_info(client, role))
            )
        
        # Tool listing tests
        results.append(
            ("List Tools (developer)", 
             await test_list_tools(client, "developer", "mcp-github"))
        )
        
        # Authorization tests
        results.append(("Authorization", await test_authorization(client)))
        
        # Metrics test
        results.append(("Metrics", await test_metrics(client)))
        
        # Summary
        print_header("Test Summary")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            if result:
                print_success(f"{test_name}")
            else:
                print_error(f"{test_name}")
        
        print(f"\n{BLUE}{'=' * 60}{RESET}")
        if passed == total:
            print(f"{GREEN}All tests passed! ({passed}/{total}){RESET}")
            print(f"{BLUE}{'=' * 60}{RESET}\n")
            return 0
        else:
            print(f"{YELLOW}Some tests failed: {passed}/{total} passed{RESET}")
            print(f"{BLUE}{'=' * 60}{RESET}\n")
            return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Tests interrupted by user{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Test suite error: {e}{RESET}")
        sys.exit(1)
