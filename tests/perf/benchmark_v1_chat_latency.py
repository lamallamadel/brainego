#!/usr/bin/env python3
"""Benchmark end-to-end latency and throughput for /v1/chat."""

import argparse
import concurrent.futures
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib import request, error

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_ITERATIONS = 10
DEFAULT_CONCURRENCY = 2
DEFAULT_TIMEOUT_S = 120
DEFAULT_WARMUP = 2
GOAL_STANDARD_RAG_P95_MS = 3000.0


@dataclass
class RequestResult:
    status_code: int
    latency_ms: float
    success: bool
    error: str = ""


SCENARIOS: List[Dict[str, Any]] = [
    {
        "name": "standard_rag_query",
        "description": "Standard knowledge-grounded query (baseline goal: p95 < 3s)",
        "goal": {"p95_latency_ms_lt": GOAL_STANDARD_RAG_P95_MS},
        "payload": {
            "model": "llama-3.3-8b-instruct",
            "messages": [
                {"role": "user", "content": "Summarize the deployment prerequisites for this platform."}
            ],
            "temperature": 0.2,
            "max_tokens": 180,
            "stream": False,
            "use_rag": True,
            "use_memory": False,
            "store_memory": False,
            "rag_k": 5,
        },
    },
    {
        "name": "memory_follow_up",
        "description": "Conversational follow-up with memory retrieval enabled",
        "payload": {
            "model": "llama-3.3-8b-instruct",
            "messages": [
                {"role": "user", "content": "I am preparing an offline deployment. Any quick checklist?"},
                {"role": "assistant", "content": "Sure, focus on dependencies, configs, and health checks."},
                {"role": "user", "content": "Great. Based on that, give me the top 3 risks to monitor."},
            ],
            "temperature": 0.3,
            "max_tokens": 220,
            "stream": False,
            "use_rag": True,
            "use_memory": True,
            "store_memory": True,
            "memory_top_k": 5,
        },
    },
    {
        "name": "chat_without_rag",
        "description": "Plain chat response without RAG/memory enrichment",
        "payload": {
            "model": "llama-3.3-8b-instruct",
            "messages": [
                {"role": "user", "content": "Explain in two sentences what retrieval augmented generation is."}
            ],
            "temperature": 0.5,
            "max_tokens": 120,
            "stream": False,
            "use_rag": False,
            "use_memory": False,
            "store_memory": False,
        },
    },
]


def percentile(values: List[float], p: float) -> float:
    if not values:
        return math.nan
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def send_request(base_url: str, payload: Dict[str, Any], timeout_s: int) -> RequestResult:
    endpoint = f"{base_url.rstrip('/')}/v1/chat"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = request.Request(endpoint, data=data, headers=headers, method="POST")
    start = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            _ = resp.read()
            latency_ms = (time.perf_counter() - start) * 1000
            status_code = getattr(resp, "status", 200)
            return RequestResult(status_code=status_code, latency_ms=latency_ms, success=(status_code == 200))
    except error.HTTPError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        return RequestResult(status_code=exc.code, latency_ms=latency_ms, success=False, error=str(exc))
    except Exception as exc:  # pylint: disable=broad-except
        latency_ms = (time.perf_counter() - start) * 1000
        return RequestResult(status_code=0, latency_ms=latency_ms, success=False, error=str(exc))


def run_scenario(base_url: str, scenario: Dict[str, Any], iterations: int, concurrency: int, timeout_s: int) -> Dict[str, Any]:
    started_at = time.perf_counter()
    results: List[RequestResult] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(send_request, base_url, scenario["payload"], timeout_s) for _ in range(iterations)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    elapsed_s = time.perf_counter() - started_at
    latencies = [r.latency_ms for r in results]
    successes = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    summary = {
        "name": scenario["name"],
        "description": scenario["description"],
        "iterations": iterations,
        "concurrency": concurrency,
        "duration_s": elapsed_s,
        "throughput_rps": (len(results) / elapsed_s) if elapsed_s > 0 else 0.0,
        "success_count": len(successes),
        "failure_count": len(failed),
        "success_rate": (len(successes) / len(results)) if results else 0.0,
        "latency_ms": {
            "min": min(latencies) if latencies else math.nan,
            "max": max(latencies) if latencies else math.nan,
            "mean": statistics.mean(latencies) if latencies else math.nan,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "errors": [r.error for r in failed[:5]],
    }

    goal = scenario.get("goal")
    if goal:
        p95_limit = goal.get("p95_latency_ms_lt")
        if p95_limit is not None:
            summary["goal"] = {
                "p95_latency_ms_lt": p95_limit,
                "passed": summary["latency_ms"]["p95"] < p95_limit,
            }

    return summary


def format_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# /v1/chat End-to-End Benchmark Report",
        "",
        f"- Timestamp (UTC): `{report['metadata']['timestamp_utc']}`",
        f"- Base URL: `{report['metadata']['base_url']}`",
        f"- Iterations per scenario: `{report['metadata']['iterations']}`",
        f"- Concurrency: `{report['metadata']['concurrency']}`",
        "",
        "## Scenario Results",
        "",
        "| Scenario | Success Rate | Throughput (req/s) | P50 (ms) | P95 (ms) | P99 (ms) | Goal |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    for scenario in report["scenarios"]:
        goal_text = "-"
        goal = scenario.get("goal")
        if goal:
            limit = goal["p95_latency_ms_lt"]
            status = "✅ PASS" if goal["passed"] else "❌ FAIL"
            goal_text = f"{status} (p95 < {limit:.0f}ms)"

        lines.append(
            f"| {scenario['name']} | {scenario['success_rate'] * 100:.1f}% | {scenario['throughput_rps']:.2f} | "
            f"{scenario['latency_ms']['p50']:.2f} | {scenario['latency_ms']['p95']:.2f} | {scenario['latency_ms']['p99']:.2f} | {goal_text} |"
        )

    lines.append("")
    lines.append("## Notes")
    lines.append("- Goal for standard RAG query: p95 latency < 3000 ms.")
    lines.append("- Run multiple times and compare medians for a stable baseline.")
    lines.append("- Investigate scenarios with low success rates before trusting latency numbers.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark /v1/chat latency and throughput")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS, help="Requests per scenario")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Concurrent workers")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Per-request timeout in seconds")
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP, help="Warmup requests to /health")
    parser.add_argument(
        "--output",
        default="tests/perf/artifacts/v1_chat_benchmark_report.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def warmup(base_url: str, warmup_count: int, timeout_s: int) -> None:
    health_endpoint = f"{base_url.rstrip('/')}/health"
    for _ in range(warmup_count):
        req = request.Request(health_endpoint, method="GET")
        with request.urlopen(req, timeout=timeout_s) as resp:
            _ = resp.read()


def main() -> int:
    args = parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = output_path.with_suffix(".md")

    try:
        warmup(args.base_url, args.warmup, args.timeout)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Warmup failed against {args.base_url}/health: {exc}")
        return 1

    scenarios = [run_scenario(args.base_url, scenario, args.iterations, args.concurrency, args.timeout) for scenario in SCENARIOS]
    report = {
        "metadata": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "base_url": args.base_url,
            "iterations": args.iterations,
            "concurrency": args.concurrency,
            "timeout_s": args.timeout,
            "warmup": args.warmup,
        },
        "scenarios": scenarios,
    }

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(format_markdown(report), encoding="utf-8")

    print(f"JSON report written to: {output_path}")
    print(f"Markdown summary written to: {markdown_path}")

    standard = next((scenario for scenario in scenarios if scenario["name"] == "standard_rag_query"), None)
    if standard and "goal" in standard:
        passed = standard["goal"]["passed"]
        status = "PASS" if passed else "FAIL"
        print(
            f"Goal check [{status}] standard_rag_query p95={standard['latency_ms']['p95']:.2f}ms "
            f"(target < {standard['goal']['p95_latency_ms_lt']:.0f}ms)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
