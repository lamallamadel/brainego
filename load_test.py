#!/usr/bin/env python3
"""
Load testing script for MAX Serve API with latency metrics (P50/P95/P99).
Tests the /v1/chat/completions endpoint with various concurrent request patterns.
"""

import asyncio
import time
import json
import statistics
import argparse
import sys
from typing import Any, Dict, List
from datetime import datetime
from dataclasses import dataclass, asdict

# Test configuration
API_BASE_URL = "http://localhost:8000"
CHAT_COMPLETIONS_URL = f"{API_BASE_URL}/v1/chat/completions"
HEALTH_URL = f"{API_BASE_URL}/health"


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser for the load-test runner."""
    parser = argparse.ArgumentParser(description="Load test MAX Serve API")
    parser.add_argument("--url", default=API_BASE_URL, help="API base URL")
    parser.add_argument("--requests", type=int, default=100, help="Number of requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent requests")
    parser.add_argument("--max-tokens", type=int, default=100, help="Max tokens per request")
    parser.add_argument(
        "--scenario",
        choices=["short", "medium", "long", "all"],
        default="medium",
        help="Test scenario",
    )
    parser.add_argument("--output", default="load_test_report.json", help="Output JSON file")
    return parser


@dataclass
class TestResult:
    """Individual test request result."""
    request_id: int
    status_code: int
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    error: str = ""
    success: bool = True


@dataclass
class LoadTestReport:
    """Load test summary report."""
    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    duration_seconds: float
    requests_per_second: float
    
    # Latency metrics
    min_latency_ms: float
    max_latency_ms: float
    mean_latency_ms: float
    median_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    stddev_latency_ms: float
    
    # Token metrics
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    avg_tokens_per_request: float
    total_tokens_per_second: float
    completion_tokens_per_second: float
    
    timestamp: str


class LoadTester:
    def __init__(self, httpx_module: Any, base_url: str = API_BASE_URL):
        self.httpx = httpx_module
        self.base_url = base_url
        self.chat_completions_url = f"{base_url}/v1/chat/completions"
        self.health_url = f"{base_url}/health"
        self.results: List[TestResult] = []
        
    async def check_health(self) -> bool:
        """Check if the API is healthy."""
        try:
            async with self.httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.health_url)
                if response.status_code == 200:
                    data = response.json()
                    print(f"✓ Health check passed: {data.get('status')}")
                    print(f"  MAX Serve status: {data.get('max_serve_status')}")
                    return True
                else:
                    print(f"✗ Health check failed: HTTP {response.status_code}")
                    return False
        except Exception as e:
            print(f"✗ Health check failed: {e}")
            return False
    
    async def send_request(
        self,
        request_id: int,
        messages: List[Dict[str, str]],
        max_tokens: int = 100,
        temperature: float = 0.7
    ) -> TestResult:
        """Send a single chat completion request."""
        
        payload = {
            "model": "llama-3.3-8b-instruct",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        start_time = time.time()
        
        try:
            async with self.httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(self.chat_completions_url, json=payload)
                latency_ms = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usage", {})
                    
                    return TestResult(
                        request_id=request_id,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        success=True
                    )
                else:
                    return TestResult(
                        request_id=request_id,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        error=f"HTTP {response.status_code}",
                        success=False
                    )
                    
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return TestResult(
                request_id=request_id,
                status_code=0,
                latency_ms=latency_ms,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                error=str(e),
                success=False
            )
    
    async def run_concurrent_requests(
        self,
        num_requests: int,
        concurrency: int,
        messages: List[Dict[str, str]],
        max_tokens: int = 100
    ) -> List[TestResult]:
        """Run multiple requests with specified concurrency."""
        
        results = []
        semaphore = asyncio.Semaphore(concurrency)
        
        async def limited_request(req_id: int):
            async with semaphore:
                return await self.send_request(req_id, messages, max_tokens)
        
        tasks = [limited_request(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks)
        
        return results
    
    def calculate_percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile from a list of values."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * (percentile / 100.0))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]
    
    def generate_report(self, test_name: str, results: List[TestResult], duration: float) -> LoadTestReport:
        """Generate a comprehensive test report."""
        
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        latencies = [r.latency_ms for r in successful_results]
        
        if not latencies:
            latencies = [0.0]
        
        total_prompt_tokens = sum(r.prompt_tokens for r in successful_results)
        total_completion_tokens = sum(r.completion_tokens for r in successful_results)
        total_tokens = sum(r.total_tokens for r in successful_results)
        
        report = LoadTestReport(
            test_name=test_name,
            total_requests=len(results),
            successful_requests=len(successful_results),
            failed_requests=len(failed_results),
            duration_seconds=duration,
            requests_per_second=len(results) / duration if duration > 0 else 0,
            
            min_latency_ms=min(latencies),
            max_latency_ms=max(latencies),
            mean_latency_ms=statistics.mean(latencies),
            median_latency_ms=statistics.median(latencies),
            p50_latency_ms=self.calculate_percentile(latencies, 50),
            p95_latency_ms=self.calculate_percentile(latencies, 95),
            p99_latency_ms=self.calculate_percentile(latencies, 99),
            stddev_latency_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
            
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_tokens=total_tokens,
            avg_tokens_per_request=total_tokens / len(successful_results) if successful_results else 0,
            total_tokens_per_second=total_tokens / duration if duration > 0 else 0.0,
            completion_tokens_per_second=(
                total_completion_tokens / duration if duration > 0 else 0.0
            ),
            
            timestamp=datetime.utcnow().isoformat()
        )
        
        return report
    
    def print_report(self, report: LoadTestReport):
        """Print formatted test report."""
        
        print("\n" + "=" * 80)
        print(f"LOAD TEST REPORT: {report.test_name}")
        print("=" * 80)
        
        print(f"\n📊 Request Summary:")
        print(f"  Total Requests:      {report.total_requests}")
        print(f"  Successful:          {report.successful_requests} ({report.successful_requests/report.total_requests*100:.1f}%)")
        print(f"  Failed:              {report.failed_requests} ({report.failed_requests/report.total_requests*100:.1f}%)")
        print(f"  Duration:            {report.duration_seconds:.2f}s")
        print(f"  Throughput:          {report.requests_per_second:.2f} req/s")
        
        print(f"\n⚡ Latency Metrics (milliseconds):")
        print(f"  Min:                 {report.min_latency_ms:.2f} ms")
        print(f"  Max:                 {report.max_latency_ms:.2f} ms")
        print(f"  Mean:                {report.mean_latency_ms:.2f} ms")
        print(f"  Median:              {report.median_latency_ms:.2f} ms")
        print(f"  P50 (50th percentile): {report.p50_latency_ms:.2f} ms")
        print(f"  P95 (95th percentile): {report.p95_latency_ms:.2f} ms")
        print(f"  P99 (99th percentile): {report.p99_latency_ms:.2f} ms")
        print(f"  Std Dev:             {report.stddev_latency_ms:.2f} ms")
        
        print(f"\n🔤 Token Usage:")
        print(f"  Total Prompt Tokens:     {report.total_prompt_tokens}")
        print(f"  Total Completion Tokens: {report.total_completion_tokens}")
        print(f"  Total Tokens:            {report.total_tokens}")
        print(f"  Avg Tokens/Request:      {report.avg_tokens_per_request:.1f}")
        print(f"  Total Tokens/sec:        {report.total_tokens_per_second:.2f}")
        print(f"  Completion Tokens/sec:   {report.completion_tokens_per_second:.2f}")
        
        print("\n" + "=" * 80 + "\n")
    
    def save_report(self, report: LoadTestReport, filename: str):
        """Save report to JSON file."""
        with open(filename, 'w') as f:
            json.dump(asdict(report), f, indent=2)
        print(f"📄 Report saved to: {filename}")


# Test scenarios
TEST_MESSAGES_SHORT = [
    {"role": "user", "content": "Hello! How are you?"}
]

TEST_MESSAGES_MEDIUM = [
    {"role": "system", "content": "You are a helpful AI assistant."},
    {"role": "user", "content": "Explain quantum computing in simple terms."}
]

TEST_MESSAGES_LONG = [
    {"role": "system", "content": "You are an expert software engineer with deep knowledge of Python, system design, and best practices."},
    {"role": "user", "content": "I need help designing a scalable microservices architecture for an e-commerce platform. The system should handle 10,000 requests per second, support real-time inventory updates, and integrate with multiple payment gateways. What would be your recommended approach?"}
]


async def async_main(args: argparse.Namespace, httpx_module: Any):
    """Run asynchronous load tests with parsed CLI arguments."""
    tester = LoadTester(httpx_module=httpx_module, base_url=args.url)
    
    print(f"🚀 Starting Load Test")
    print(f"   API URL: {args.url}")
    print(f"   Requests: {args.requests}")
    print(f"   Concurrency: {args.concurrency}")
    print(f"   Max Tokens: {args.max_tokens}")
    print(f"   Scenario: {args.scenario}")
    print()
    
    # Health check
    print("Checking API health...")
    if not await tester.check_health():
        print("❌ API is not healthy. Aborting test.")
        return
    
    print()
    
    # Select test scenarios
    scenarios = []
    if args.scenario == "short" or args.scenario == "all":
        scenarios.append(("Short Prompt", TEST_MESSAGES_SHORT))
    if args.scenario == "medium" or args.scenario == "all":
        scenarios.append(("Medium Prompt", TEST_MESSAGES_MEDIUM))
    if args.scenario == "long" or args.scenario == "all":
        scenarios.append(("Long Prompt", TEST_MESSAGES_LONG))
    
    all_reports = []
    
    for scenario_name, messages in scenarios:
        print(f"Running test: {scenario_name}")
        print(f"  Messages: {len(messages)}")
        print(f"  Starting {args.requests} requests with concurrency {args.concurrency}...")
        
        start_time = time.time()
        results = await tester.run_concurrent_requests(
            num_requests=args.requests,
            concurrency=args.concurrency,
            messages=messages,
            max_tokens=args.max_tokens
        )
        duration = time.time() - start_time
        
        report = tester.generate_report(scenario_name, results, duration)
        tester.print_report(report)
        all_reports.append(report)
    
    # Save combined report
    if len(all_reports) == 1:
        tester.save_report(all_reports[0], args.output)
    else:
        combined_output = {
            "test_suite": "Load Test - Multiple Scenarios",
            "timestamp": datetime.utcnow().isoformat(),
            "reports": [asdict(r) for r in all_reports]
        }
        with open(args.output, 'w') as f:
            json.dump(combined_output, f, indent=2)
        print(f"📄 Combined report saved to: {args.output}")
    
    print("\n✅ Load test completed!")


def main(argv: List[str] | None = None) -> int:
    """Parse args and run load tests."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        import httpx as httpx_module
    except ImportError:
        print(
            "Missing dependency: httpx. Install it with `pip install -r requirements.txt`.",
            file=sys.stderr,
        )
        return 2

    asyncio.run(async_main(args, httpx_module))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
