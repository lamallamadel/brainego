#!/usr/bin/env python3
"""Smoke tests for MAX Serve API endpoints with baseline latency and token metrics."""

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List


DEFAULT_API_BASE_URL = "http://localhost:8000"


@dataclass
class SmokeResult:
    """Individual smoke test request result."""

    name: str
    status_code: int
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    success: bool
    error: str = ""


TEST_PROMPTS = [
    (
        "short",
        [
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "Reply with one sentence about latency testing."},
        ],
        60,
    ),
    (
        "medium",
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": "Summarize why smoke tests and load tests matter for inference APIs.",
            },
        ],
        120,
    ),
    (
        "long",
        [
            {
                "role": "system",
                "content": "You are an expert in distributed AI inference systems.",
            },
            {
                "role": "user",
                "content": (
                    "Describe a practical baseline testing strategy for a chat completion endpoint "
                    "that includes latency percentiles and throughput-oriented token metrics."
                ),
            },
        ],
        180,
    ),
]


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for smoke tests."""
    parser = argparse.ArgumentParser(description="Smoke test MAX Serve API endpoint")
    parser.add_argument("--url", default=DEFAULT_API_BASE_URL, help="API base URL")
    return parser


def calculate_percentile(values: List[float], percentile: int) -> float:
    """Calculate a percentile using nearest-rank behavior."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * (percentile / 100.0))
    index = min(index, len(sorted_values) - 1)
    return sorted_values[index]


def test_health(base_url: str, requests_module: Any) -> bool:
    """Test the /health endpoint."""
    print("Testing /health endpoint...")
    response = requests_module.get(f"{base_url}/health", timeout=15)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    print()
    return response.status_code == 200


def run_smoke_prompt_test(
    base_url: str,
    name: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    requests_module: Any,
) -> SmokeResult:
    """Run a single smoke prompt test request."""
    payload = {
        "model": "llama-3.3-8b-instruct",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": False,
    }

    start_time = time.time()
    try:
        response = requests_module.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            timeout=300,
        )
        latency_ms = (time.time() - start_time) * 1000
        if response.status_code != 200:
            return SmokeResult(
                name=name,
                status_code=response.status_code,
                latency_ms=latency_ms,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                success=False,
                error=response.text,
            )

        data = response.json()
        usage = data.get("usage", {})
        return SmokeResult(
            name=name,
            status_code=response.status_code,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            success=True,
        )
    except Exception as exc:  # pragma: no cover
        latency_ms = (time.time() - start_time) * 1000
        return SmokeResult(
            name=name,
            status_code=0,
            latency_ms=latency_ms,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            success=False,
            error=str(exc),
        )


def print_smoke_report(results: List[SmokeResult], duration_seconds: float) -> bool:
    """Print smoke-test report with baseline metrics."""
    succeeded = [result for result in results if result.success]
    failed = [result for result in results if not result.success]

    latencies = [result.latency_ms for result in succeeded]
    total_prompt_tokens = sum(result.prompt_tokens for result in succeeded)
    total_completion_tokens = sum(result.completion_tokens for result in succeeded)
    total_tokens = sum(result.total_tokens for result in succeeded)
    tokens_per_second = total_tokens / duration_seconds if duration_seconds > 0 else 0.0

    print("=" * 80)
    print("SMOKE TEST BASELINE REPORT")
    print("=" * 80)
    print(f"Executed prompts: {len(results)}")
    print(f"Successful:       {len(succeeded)}")
    print(f"Failed:           {len(failed)}")
    print(f"Total duration:   {duration_seconds:.2f}s")

    if latencies:
        print("\nLatency metrics (ms):")
        print(f"  P50: {calculate_percentile(latencies, 50):.2f}")
        print(f"  P95: {calculate_percentile(latencies, 95):.2f}")
        print(f"  P99: {calculate_percentile(latencies, 99):.2f}")

    print("\nToken baseline:")
    print(f"  Prompt tokens:      {total_prompt_tokens}")
    print(f"  Completion tokens:  {total_completion_tokens}")
    print(f"  Total tokens:       {total_tokens}")
    print(f"  Tokens/sec:         {tokens_per_second:.2f}")

    if failed:
        print("\nFailed request details:")
        for result in failed:
            print(f"  - {result.name}: status={result.status_code} error={result.error}")

    print("=" * 80)
    return not failed


def main(argv: List[str] | None = None) -> int:
    """Run smoke tests against MAX endpoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        import requests as requests_module
    except ImportError:
        print(
            "Missing dependency: requests. Install it with `pip install -r requirements.txt`.",
            file=sys.stderr,
        )
        return 2

    print("=" * 80)
    print("MAX ENDPOINT SMOKE TEST")
    print("=" * 80)

    if not test_health(args.url, requests_module):
        print("❌ Health check failed; aborting smoke test run.")
        return 1

    results: List[SmokeResult] = []
    start_time = time.time()
    for name, messages, max_tokens in TEST_PROMPTS:
        print(f"Running synthetic prompt: {name}")
        result = run_smoke_prompt_test(args.url, name, messages, max_tokens, requests_module)
        results.append(result)
        if result.success:
            print(
                f"  ✓ status={result.status_code} latency={result.latency_ms:.2f}ms "
                f"tokens={result.total_tokens}"
            )
        else:
            print(
                f"  ✗ status={result.status_code} latency={result.latency_ms:.2f}ms "
                f"error={result.error}"
            )
    duration_seconds = time.time() - start_time

    all_passed = print_smoke_report(results, duration_seconds)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
