#!/usr/bin/env python3
"""
Real-time monitoring dashboard for MAX Serve API performance.
"""

import asyncio
import time
import json
from datetime import datetime
from typing import Dict, List
import httpx
import sys


class PerformanceMonitor:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.health_url = f"{api_url}/health"
        self.metrics_url = f"{api_url}/metrics"
        self.history: List[Dict] = []
        self.max_history = 60  # Keep last 60 readings
    
    async def check_health(self) -> Dict:
        """Check API health status."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.health_url)
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}
    
    async def get_metrics(self) -> Dict:
        """Get current metrics."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.metrics_url)
                if response.status_code == 200:
                    return response.json()
                else:
                    return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def format_status(self, status: str) -> str:
        """Format status with color codes."""
        colors = {
            "healthy": "\033[92m",      # Green
            "degraded": "\033[93m",     # Yellow
            "unhealthy": "\033[91m",    # Red
            "unreachable": "\033[91m",  # Red
        }
        reset = "\033[0m"
        color = colors.get(status, "")
        return f"{color}{status.upper()}{reset}"
    
    def clear_screen(self):
        """Clear terminal screen."""
        print("\033[2J\033[H", end="")
    
    def draw_bar(self, value: float, max_value: float, width: int = 30) -> str:
        """Draw a simple progress bar."""
        if max_value == 0:
            ratio = 0
        else:
            ratio = min(value / max_value, 1.0)
        
        filled = int(ratio * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar} {value:.1f}"
    
    async def display_dashboard(self):
        """Display real-time monitoring dashboard."""
        
        while True:
            self.clear_screen()
            
            # Header
            print("=" * 80)
            print(f"MAX Serve API Performance Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            print()
            
            # Health Check
            health = await self.check_health()
            status = health.get("status", "unknown")
            
            print(f"🏥 Health Status: {self.format_status(status)}")
            print(f"   Model: {health.get('model', 'N/A')}")
            print(f"   MAX Serve: {health.get('max_serve_status', 'N/A')}")
            print()
            
            # Metrics
            metrics_data = await self.get_metrics()
            
            if "error" in metrics_data:
                print(f"❌ Metrics Error: {metrics_data['error']}")
            else:
                metrics = metrics_data.get("metrics", {})
                
                # Request Statistics
                print("📊 Request Statistics:")
                print(f"   Total Requests:  {metrics.get('request_count', 0)}")
                print(f"   Errors:          {metrics.get('errors', 0)}")
                
                error_rate = 0
                if metrics.get('request_count', 0) > 0:
                    error_rate = (metrics.get('errors', 0) / metrics.get('request_count', 0)) * 100
                print(f"   Error Rate:      {error_rate:.2f}%")
                print()
                
                # Latency Metrics
                print("⚡ Latency Metrics (milliseconds):")
                avg_latency = metrics.get('avg_latency_ms', 0)
                p50_latency = metrics.get('p50_latency_ms', 0)
                p95_latency = metrics.get('p95_latency_ms', 0)
                p99_latency = metrics.get('p99_latency_ms', 0)
                
                max_latency = max(avg_latency, p50_latency, p95_latency, p99_latency, 1000)
                
                print(f"   Average: {self.draw_bar(avg_latency, max_latency)}")
                print(f"   P50:     {self.draw_bar(p50_latency, max_latency)}")
                print(f"   P95:     {self.draw_bar(p95_latency, max_latency)}")
                print(f"   P99:     {self.draw_bar(p99_latency, max_latency)}")
                print()
                
                # Store history
                self.history.append({
                    "timestamp": time.time(),
                    "avg_latency": avg_latency,
                    "p95_latency": p95_latency,
                    "request_count": metrics.get('request_count', 0)
                })
                
                if len(self.history) > self.max_history:
                    self.history = self.history[-self.max_history:]
                
                # Trend Analysis (last 10 readings)
                if len(self.history) >= 10:
                    recent = self.history[-10:]
                    avg_trend = sum(r["avg_latency"] for r in recent) / len(recent)
                    
                    print("📈 Trends (last 10 readings):")
                    print(f"   Average Latency: {avg_trend:.2f}ms")
                    
                    if len(self.history) >= 20:
                        older = self.history[-20:-10]
                        old_avg = sum(r["avg_latency"] for r in older) / len(older)
                        trend_pct = ((avg_trend - old_avg) / old_avg * 100) if old_avg > 0 else 0
                        
                        trend_symbol = "📈" if trend_pct > 5 else "📉" if trend_pct < -5 else "➡️"
                        print(f"   Change: {trend_symbol} {trend_pct:+.1f}%")
                    print()
            
            # Footer
            print("=" * 80)
            print("Press Ctrl+C to exit | Refresh every 5 seconds")
            print("=" * 80)
            
            # Wait before next update
            await asyncio.sleep(5)
    
    async def run(self):
        """Run the monitoring dashboard."""
        try:
            await self.display_dashboard()
        except KeyboardInterrupt:
            self.clear_screen()
            print("\n👋 Monitoring stopped.")
            sys.exit(0)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor MAX Serve API performance")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()
    
    monitor = PerformanceMonitor(args.url)
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
