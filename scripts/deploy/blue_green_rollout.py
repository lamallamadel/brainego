#!/usr/bin/env python3
"""
Blue-Green Deployment Rollout Orchestrator

Automates blue-green deployments with weighted traffic routing, health monitoring,
and automated rollback on failure detection.

Features:
- Deploy new version to green environment
- Run smoke tests against green endpoints
- Gradually shift traffic: 90/10 → 50/50 → 10/90 → 0/100
- Monitor error rates and P99 latency during soak periods
- Automated rollback on threshold violations
- One-click manual rollback command
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

# Needs: python-package:requests>=2.31.0
try:
    import requests
except ImportError:
    print("Error: requests package not available")
    print("Install with: pip install requests>=2.31.0")
    sys.exit(1)


class DeploymentPhase(Enum):
    """Deployment phases"""
    INIT = "init"
    DEPLOY_GREEN = "deploy_green"
    SMOKE_TEST = "smoke_test"
    TRAFFIC_10 = "traffic_10"
    TRAFFIC_50 = "traffic_50"
    TRAFFIC_90 = "traffic_90"
    TRAFFIC_100 = "traffic_100"
    COMPLETE = "complete"
    ROLLBACK = "rollback"
    FAILED = "failed"


@dataclass
class HealthMetrics:
    """Health metrics for monitoring"""
    error_rate: float
    p99_latency: float
    request_count: int
    success_count: int
    timestamp: datetime


@dataclass
class TrafficSplit:
    """Traffic split configuration"""
    blue: int
    green: int


class BlueGreenRollout:
    """Blue-Green deployment orchestrator"""
    
    def __init__(self, 
                 namespace: str,
                 service_name: str,
                 new_image_tag: str,
                 prometheus_url: str,
                 ingress_name: str,
                 error_rate_threshold: float = 0.01,
                 p99_latency_threshold: float = 3.0,
                 soak_period_seconds: int = 300,
                 smoke_test_url: Optional[str] = None,
                 dry_run: bool = False):
        """Initialize rollout orchestrator"""
        self.namespace = namespace
        self.service_name = service_name
        self.new_image_tag = new_image_tag
        self.prometheus_url = prometheus_url
        self.ingress_name = ingress_name
        self.error_rate_threshold = error_rate_threshold
        self.p99_latency_threshold = p99_latency_threshold
        self.soak_period_seconds = soak_period_seconds
        self.smoke_test_url = smoke_test_url
        self.dry_run = dry_run
        
        self.phase = DeploymentPhase.INIT
        self.start_time = datetime.now()
        
        self.traffic_splits = [
            TrafficSplit(blue=90, green=10),
            TrafficSplit(blue=50, green=50),
            TrafficSplit(blue=10, green=90),
            TrafficSplit(blue=0, green=100),
        ]
    
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = "🔵🟢" if level == "INFO" else "⚠️" if level == "WARN" else "❌"
        print(f"[{timestamp}] {prefix} {level}: {message}")
    
    def run_kubectl(self, args: List[str]) -> Tuple[bool, str]:
        """Execute kubectl command"""
        cmd = ["kubectl"] + args
        
        if self.dry_run:
            self.log(f"DRY RUN: {' '.join(cmd)}")
            return True, "dry-run"
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stderr
    
    def update_green_deployment(self) -> bool:
        """Update green deployment with new image"""
        self.log(f"Updating green deployment to image tag: {self.new_image_tag}")
        
        success, output = self.run_kubectl([
            "set", "image",
            f"deployment/{self.service_name}-green",
            f"{self.service_name}={self.service_name}:{self.new_image_tag}",
            "-n", self.namespace
        ])
        
        if not success:
            self.log(f"Failed to update green deployment: {output}", "ERROR")
            return False
        
        self.log("Green deployment updated successfully")
        return True
    
    def wait_for_green_ready(self, timeout: int = 600) -> bool:
        """Wait for green deployment to be ready"""
        self.log(f"Waiting for green deployment to be ready (timeout: {timeout}s)")
        
        success, output = self.run_kubectl([
            "rollout", "status",
            f"deployment/{self.service_name}-green",
            "-n", self.namespace,
            f"--timeout={timeout}s"
        ])
        
        if not success:
            self.log(f"Green deployment failed to become ready: {output}", "ERROR")
            return False
        
        self.log("Green deployment is ready")
        return True
    
    def run_smoke_tests(self) -> bool:
        """Run smoke tests against green endpoints"""
        if not self.smoke_test_url:
            self.log("No smoke test URL configured, skipping smoke tests", "WARN")
            return True
        
        self.log(f"Running smoke tests against: {self.smoke_test_url}")
        
        green_url = self.smoke_test_url.replace("-blue", "-green")
        
        tests = [
            {"name": "Health Check", "path": "/health", "method": "GET"},
            {"name": "Readiness Check", "path": "/ready", "method": "GET"},
            {"name": "Metrics Check", "path": "/metrics", "method": "GET"},
        ]
        
        for test in tests:
            url = f"{green_url}{test['path']}"
            self.log(f"Testing: {test['name']} - {url}")
            
            try:
                if self.dry_run:
                    self.log(f"DRY RUN: Would test {url}")
                    continue
                
                response = requests.get(url, timeout=30)
                
                if response.status_code == 200:
                    self.log(f"✓ {test['name']} passed")
                else:
                    self.log(f"✗ {test['name']} failed: HTTP {response.status_code}", "ERROR")
                    return False
            
            except requests.exceptions.RequestException as e:
                self.log(f"✗ {test['name']} failed: {e}", "ERROR")
                return False
        
        self.log("All smoke tests passed")
        return True
    
    def update_traffic_split(self, split: TrafficSplit) -> bool:
        """Update ingress traffic split"""
        self.log(f"Updating traffic split: Blue {split.blue}% / Green {split.green}%")
        
        success, output = self.run_kubectl([
            "annotate", "ingress", f"{self.ingress_name}-green-canary",
            f"nginx.ingress.kubernetes.io/canary-weight={split.green}",
            "-n", self.namespace,
            "--overwrite"
        ])
        
        if not success:
            self.log(f"Failed to update traffic split: {output}", "ERROR")
            return False
        
        self.log(f"Traffic split updated: Blue {split.blue}% / Green {split.green}%")
        return True
    
    def get_metrics_from_prometheus(self, environment: str) -> Optional[HealthMetrics]:
        """Query Prometheus for health metrics"""
        if self.dry_run:
            return HealthMetrics(
                error_rate=0.001,
                p99_latency=0.5,
                request_count=1000,
                success_count=999,
                timestamp=datetime.now()
            )
        
        try:
            error_rate_query = f'sum(rate(http_requests_total{{environment="{environment}",status=~"5.."}}[5m])) / sum(rate(http_requests_total{{environment="{environment}"}}[5m]))'
            latency_query = f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{environment="{environment}"}}[5m])) by (le))'
            request_count_query = f'sum(increase(http_requests_total{{environment="{environment}"}}[5m]))'
            
            error_rate = self._query_prometheus(error_rate_query)
            p99_latency = self._query_prometheus(latency_query)
            request_count = self._query_prometheus(request_count_query)
            
            if error_rate is None or p99_latency is None or request_count is None:
                self.log(f"Failed to retrieve metrics for {environment}", "WARN")
                return None
            
            success_count = int(request_count * (1 - error_rate))
            
            return HealthMetrics(
                error_rate=error_rate,
                p99_latency=p99_latency,
                request_count=int(request_count),
                success_count=success_count,
                timestamp=datetime.now()
            )
        
        except Exception as e:
            self.log(f"Error querying Prometheus: {e}", "ERROR")
            return None
    
    def _query_prometheus(self, query: str) -> Optional[float]:
        """Execute Prometheus query"""
        try:
            url = f"{self.prometheus_url}/api/v1/query"
            response = requests.get(url, params={"query": query}, timeout=10)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if data["status"] != "success":
                return None
            
            result = data["data"]["result"]
            
            if not result:
                return 0.0
            
            return float(result[0]["value"][1])
        
        except Exception:
            return None
    
    def monitor_soak_period(self, environment: str, duration: int) -> bool:
        """Monitor environment during soak period"""
        self.log(f"Starting {duration}s soak period for {environment} environment")
        
        start_time = time.time()
        check_interval = 30
        
        while time.time() - start_time < duration:
            elapsed = int(time.time() - start_time)
            remaining = duration - elapsed
            
            self.log(f"Soak period: {elapsed}s elapsed, {remaining}s remaining")
            
            metrics = self.get_metrics_from_prometheus(environment)
            
            if metrics:
                self.log(f"Metrics: Error Rate={metrics.error_rate:.4f}, P99 Latency={metrics.p99_latency:.3f}s, Requests={metrics.request_count}")
                
                if metrics.error_rate > self.error_rate_threshold:
                    self.log(f"ERROR RATE SPIKE DETECTED: {metrics.error_rate:.4f} > {self.error_rate_threshold}", "ERROR")
                    return False
                
                if metrics.p99_latency > self.p99_latency_threshold:
                    self.log(f"P99 LATENCY SPIKE DETECTED: {metrics.p99_latency:.3f}s > {self.p99_latency_threshold}s", "ERROR")
                    return False
            else:
                self.log("Unable to retrieve metrics, continuing monitoring", "WARN")
            
            if remaining > 0:
                sleep_time = min(check_interval, remaining)
                time.sleep(sleep_time)
        
        self.log(f"Soak period completed successfully for {environment}")
        return True
    
    def rollback_to_blue(self) -> bool:
        """Rollback traffic to blue environment"""
        self.log("INITIATING ROLLBACK TO BLUE ENVIRONMENT", "ERROR")
        
        success = self.update_traffic_split(TrafficSplit(blue=100, green=0))
        
        if success:
            self.log("ROLLBACK COMPLETE: All traffic directed to blue environment")
        else:
            self.log("ROLLBACK FAILED: Manual intervention required", "ERROR")
        
        return success
    
    def execute_rollout(self) -> bool:
        """Execute complete blue-green rollout"""
        self.log("=" * 80)
        self.log("BLUE-GREEN DEPLOYMENT ROLLOUT STARTED")
        self.log("=" * 80)
        self.log(f"Namespace: {self.namespace}")
        self.log(f"Service: {self.service_name}")
        self.log(f"New Image Tag: {self.new_image_tag}")
        self.log(f"Error Rate Threshold: {self.error_rate_threshold * 100}%")
        self.log(f"P99 Latency Threshold: {self.p99_latency_threshold}s")
        self.log(f"Soak Period: {self.soak_period_seconds}s")
        self.log(f"Dry Run: {self.dry_run}")
        self.log("=" * 80)
        
        try:
            self.phase = DeploymentPhase.DEPLOY_GREEN
            self.log(f"Phase: {self.phase.value}")
            
            if not self.update_green_deployment():
                raise Exception("Failed to update green deployment")
            
            if not self.wait_for_green_ready():
                raise Exception("Green deployment failed to become ready")
            
            self.phase = DeploymentPhase.SMOKE_TEST
            self.log(f"Phase: {self.phase.value}")
            
            if not self.run_smoke_tests():
                raise Exception("Smoke tests failed")
            
            for i, split in enumerate(self.traffic_splits):
                phase_map = {
                    0: DeploymentPhase.TRAFFIC_10,
                    1: DeploymentPhase.TRAFFIC_50,
                    2: DeploymentPhase.TRAFFIC_90,
                    3: DeploymentPhase.TRAFFIC_100,
                }
                self.phase = phase_map[i]
                
                self.log("=" * 80)
                self.log(f"Phase: {self.phase.value}")
                self.log("=" * 80)
                
                if not self.update_traffic_split(split):
                    raise Exception(f"Failed to update traffic split to {split.blue}/{split.green}")
                
                if split.green < 100:
                    if not self.monitor_soak_period("green", self.soak_period_seconds):
                        raise Exception("Health check failed during soak period")
                else:
                    self.log("Final traffic split complete - monitoring for 60s")
                    if not self.monitor_soak_period("green", 60):
                        raise Exception("Health check failed during final verification")
            
            self.phase = DeploymentPhase.COMPLETE
            self.log("=" * 80)
            self.log("BLUE-GREEN DEPLOYMENT COMPLETED SUCCESSFULLY", "INFO")
            self.log("=" * 80)
            self.log("Green environment is now serving 100% of traffic")
            self.log("Blue environment is available for next deployment")
            
            elapsed = datetime.now() - self.start_time
            self.log(f"Total deployment time: {elapsed}")
            
            return True
        
        except Exception as e:
            self.phase = DeploymentPhase.FAILED
            self.log("=" * 80, "ERROR")
            self.log(f"DEPLOYMENT FAILED: {e}", "ERROR")
            self.log("=" * 80, "ERROR")
            
            self.log("Initiating automatic rollback...")
            
            if self.rollback_to_blue():
                self.phase = DeploymentPhase.ROLLBACK
                self.log("Automatic rollback completed successfully")
            else:
                self.log("Automatic rollback failed - manual intervention required", "ERROR")
            
            return False
    
    def generate_rollback_command(self) -> str:
        """Generate one-click rollback command"""
        return f"""
# One-Click Rollback Command
kubectl annotate ingress {self.ingress_name}-green-canary \\
  nginx.ingress.kubernetes.io/canary-weight=0 \\
  -n {self.namespace} \\
  --overwrite

# This will immediately route 100% traffic back to blue environment
"""


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Blue-Green Deployment Rollout Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy new version
  python blue_green_rollout.py \\
    --namespace ai-platform-prod \\
    --service-name agent-router \\
    --new-image-tag v2.1.0 \\
    --prometheus-url http://prometheus:9090

  # Dry run
  python blue_green_rollout.py \\
    --namespace ai-platform-prod \\
    --service-name agent-router \\
    --new-image-tag v2.1.0 \\
    --prometheus-url http://prometheus:9090 \\
    --dry-run

  # Custom thresholds
  python blue_green_rollout.py \\
    --namespace ai-platform-prod \\
    --service-name agent-router \\
    --new-image-tag v2.1.0 \\
    --prometheus-url http://prometheus:9090 \\
    --error-rate-threshold 0.02 \\
    --p99-latency-threshold 5.0 \\
    --soak-period 600
"""
    )
    
    parser.add_argument(
        "--namespace",
        required=True,
        help="Kubernetes namespace"
    )
    parser.add_argument(
        "--service-name",
        required=True,
        help="Service name (without -blue/-green suffix)"
    )
    parser.add_argument(
        "--new-image-tag",
        required=True,
        help="New image tag to deploy to green environment"
    )
    parser.add_argument(
        "--prometheus-url",
        required=True,
        help="Prometheus URL for metrics (e.g., http://prometheus:9090)"
    )
    parser.add_argument(
        "--ingress-name",
        help="Ingress name (defaults to service-name)"
    )
    parser.add_argument(
        "--error-rate-threshold",
        type=float,
        default=0.01,
        help="Error rate threshold (0.01 = 1%%) (default: 0.01)"
    )
    parser.add_argument(
        "--p99-latency-threshold",
        type=float,
        default=3.0,
        help="P99 latency threshold in seconds (default: 3.0)"
    )
    parser.add_argument(
        "--soak-period",
        type=int,
        default=300,
        help="Soak period duration in seconds (default: 300)"
    )
    parser.add_argument(
        "--smoke-test-url",
        help="Base URL for smoke tests (e.g., http://agent-router-green:8000)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - simulate without making changes"
    )
    
    args = parser.parse_args()
    
    ingress_name = args.ingress_name or args.service_name
    
    rollout = BlueGreenRollout(
        namespace=args.namespace,
        service_name=args.service_name,
        new_image_tag=args.new_image_tag,
        prometheus_url=args.prometheus_url,
        ingress_name=ingress_name,
        error_rate_threshold=args.error_rate_threshold,
        p99_latency_threshold=args.p99_latency_threshold,
        soak_period_seconds=args.soak_period,
        smoke_test_url=args.smoke_test_url,
        dry_run=args.dry_run
    )
    
    success = rollout.execute_rollout()
    
    if not success:
        print("\n" + "=" * 80)
        print("ROLLBACK COMMAND")
        print("=" * 80)
        print(rollout.generate_rollback_command())
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
