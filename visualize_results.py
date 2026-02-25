#!/usr/bin/env python3
"""
Visualize load test results from JSON report.
Generates ASCII charts and statistics.
"""

import json
import sys
from typing import Dict, List


def load_report(filename: str) -> Dict:
    """Load JSON report file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{filename}'.")
        sys.exit(1)


def draw_horizontal_bar(label: str, value: float, max_value: float, width: int = 50) -> str:
    """Draw a horizontal bar chart."""
    if max_value == 0:
        ratio = 0
    else:
        ratio = min(value / max_value, 1.0)
    
    filled = int(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{label:20s} {bar} {value:.2f}ms"


def print_section_header(title: str):
    """Print a section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def visualize_single_report(report: Dict):
    """Visualize a single test report."""
    
    print_section_header(f"Load Test Report: {report['test_name']}")
    
    # Request Summary
    print("📊 Request Summary:")
    print(f"   Total Requests:      {report['total_requests']}")
    print(f"   Successful:          {report['successful_requests']} "
          f"({report['successful_requests']/report['total_requests']*100:.1f}%)")
    print(f"   Failed:              {report['failed_requests']} "
          f"({report['failed_requests']/report['total_requests']*100:.1f}%)")
    print(f"   Duration:            {report['duration_seconds']:.2f}s")
    print(f"   Throughput:          {report['requests_per_second']:.2f} req/s")
    
    # Latency Chart
    print(f"\n⚡ Latency Distribution:")
    
    latencies = {
        "Min": report['min_latency_ms'],
        "Mean": report['mean_latency_ms'],
        "Median": report['median_latency_ms'],
        "P50": report['p50_latency_ms'],
        "P95": report['p95_latency_ms'],
        "P99": report['p99_latency_ms'],
        "Max": report['max_latency_ms'],
    }
    
    max_latency = max(latencies.values())
    
    for label, value in latencies.items():
        print(f"   {draw_horizontal_bar(label, value, max_latency)}")
    
    print(f"\n   Standard Deviation: {report['stddev_latency_ms']:.2f}ms")
    
    # Token Usage
    print(f"\n🔤 Token Usage:")
    print(f"   Total Prompt Tokens:     {report['total_prompt_tokens']:,}")
    print(f"   Total Completion Tokens: {report['total_completion_tokens']:,}")
    print(f"   Total Tokens:            {report['total_tokens']:,}")
    print(f"   Avg Tokens/Request:      {report['avg_tokens_per_request']:.1f}")
    
    # Performance Grade
    print(f"\n📈 Performance Assessment:")
    
    p95 = report['p95_latency_ms']
    success_rate = (report['successful_requests'] / report['total_requests']) * 100
    
    # Grade based on P95 latency
    if p95 < 500:
        latency_grade = "Excellent"
        latency_emoji = "🟢"
    elif p95 < 1000:
        latency_grade = "Good"
        latency_emoji = "🟡"
    elif p95 < 2000:
        latency_grade = "Fair"
        latency_emoji = "🟠"
    else:
        latency_grade = "Needs Improvement"
        latency_emoji = "🔴"
    
    # Grade based on success rate
    if success_rate >= 99.9:
        reliability_grade = "Excellent"
        reliability_emoji = "🟢"
    elif success_rate >= 99:
        reliability_grade = "Good"
        reliability_emoji = "🟡"
    elif success_rate >= 95:
        reliability_grade = "Fair"
        reliability_emoji = "🟠"
    else:
        reliability_grade = "Needs Improvement"
        reliability_emoji = "🔴"
    
    print(f"   Latency (P95):  {latency_emoji} {latency_grade} ({p95:.2f}ms)")
    print(f"   Reliability:    {reliability_emoji} {reliability_grade} ({success_rate:.2f}%)")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    
    if p95 > 1000:
        print("   - Consider increasing GPU resources or reducing batch size")
        print("   - Check GPU utilization with 'nvidia-smi'")
    
    if report['failed_requests'] > 0:
        print("   - Review error logs for failed requests")
        print("   - Check timeout settings")
    
    if report['requests_per_second'] < 10:
        print("   - Increase concurrency to better utilize batching")
        print("   - Current batch_size=32 can handle more concurrent requests")
    
    throughput_efficiency = report['requests_per_second'] / 32 * 100  # 32 is max_batch_size
    if throughput_efficiency < 50:
        print(f"   - Batch utilization is low ({throughput_efficiency:.1f}%)")
        print("   - Increase concurrent requests for better efficiency")


def visualize_multiple_reports(data: Dict):
    """Visualize multiple test reports."""
    
    print_section_header("Load Test Suite Results")
    
    reports = data.get('reports', [])
    
    if not reports:
        print("No reports found in the data.")
        return
    
    # Comparison Table
    print("📊 Test Comparison:\n")
    
    print(f"{'Test Name':25s} {'Requests':>10s} {'P50':>10s} {'P95':>10s} {'P99':>10s} {'Success':>10s}")
    print("-" * 80)
    
    for report in reports:
        success_rate = (report['successful_requests'] / report['total_requests']) * 100
        print(f"{report['test_name']:25s} "
              f"{report['total_requests']:>10d} "
              f"{report['p50_latency_ms']:>9.1f}ms "
              f"{report['p95_latency_ms']:>9.1f}ms "
              f"{report['p99_latency_ms']:>9.1f}ms "
              f"{success_rate:>9.1f}%")
    
    # Detailed reports for each test
    for report in reports:
        visualize_single_report(report)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Visualize load test results")
    parser.add_argument("report", help="Path to JSON report file")
    parser.add_argument("--format", choices=["text", "summary"], default="text",
                       help="Output format")
    
    args = parser.parse_args()
    
    data = load_report(args.report)
    
    print("\n" + "="*80)
    print("LOAD TEST RESULTS VISUALIZATION")
    print("="*80)
    
    # Check if it's a single report or multiple reports
    if 'reports' in data:
        visualize_multiple_reports(data)
    else:
        visualize_single_report(data)
    
    print("\n" + "="*80)
    print(f"Report: {args.report}")
    print(f"Generated: {data.get('timestamp', 'Unknown')}")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
