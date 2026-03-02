#!/usr/bin/env python3
"""
Resource usage analyzer for Kubernetes cluster cost optimization.

Queries Prometheus for 7-day P95 CPU/memory usage across all pods,
generates right-sizing recommendations for resource requests/limits.
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json

# Needs: python-package:requests>=2.31.0
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PrometheusClient:
    """Client for querying Prometheus metrics."""

    def __init__(self, prometheus_url: str = "http://prometheus:9090"):
        self.prometheus_url = prometheus_url.rstrip("/")
        self.timeout = 30
        logger.info(f"Initialized Prometheus client: {self.prometheus_url}")

    def query_range(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        step: str = "1h"
    ) -> Dict[str, Any]:
        """Execute a range query against Prometheus."""
        url = f"{self.prometheus_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": start_time.timestamp(),
            "end": end_time.timestamp(),
            "step": step
        }
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "success":
                raise ValueError(f"Prometheus query failed: {data.get('error')}")
            
            return data.get("data", {})
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            raise

    def query_instant(self, query: str) -> Dict[str, Any]:
        """Execute an instant query against Prometheus."""
        url = f"{self.prometheus_url}/api/v1/query"
        params = {"query": query}
        
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "success":
                raise ValueError(f"Prometheus query failed: {data.get('error')}")
            
            return data.get("data", {})
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            raise


class ResourceAnalyzer:
    """Analyzes resource usage and generates right-sizing recommendations."""

    def __init__(self, prometheus_client: PrometheusClient):
        self.prometheus = prometheus_client
        
        # Thresholds for right-sizing recommendations
        self.cpu_underutilization_threshold = 0.40  # P95 < 40% of request
        self.memory_underutilization_threshold = 0.40  # P95 < 40% of request
        self.cpu_overutilization_threshold = 0.85  # P95 > 85% of request
        self.memory_overutilization_threshold = 0.85  # P95 > 85% of request
        
        # Safety buffer for recommendations
        self.cpu_buffer = 1.2  # 20% buffer
        self.memory_buffer = 1.2  # 20% buffer

    def get_pod_cpu_usage_p95(self, lookback_days: int = 7) -> Dict[str, Dict[str, float]]:
        """Get P95 CPU usage for all pods over the lookback period."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=lookback_days)
        
        # Query for CPU usage by pod
        query = '''
        quantile_over_time(0.95,
            rate(container_cpu_usage_seconds_total{
                container!="",
                container!="POD",
                namespace="ai-platform"
            }[5m])[7d:1h]
        )
        '''
        
        logger.info(f"Querying CPU P95 usage for {lookback_days} days...")
        result = self.prometheus.query_instant(query)
        
        pod_cpu_usage = {}
        for metric in result.get("result", []):
            labels = metric.get("metric", {})
            pod = labels.get("pod", "unknown")
            container = labels.get("container", "unknown")
            namespace = labels.get("namespace", "unknown")
            
            value = float(metric.get("value", [0, 0])[1])
            
            key = f"{namespace}/{pod}/{container}"
            if key not in pod_cpu_usage:
                pod_cpu_usage[key] = {}
            
            pod_cpu_usage[key] = {
                "p95_cores": value,
                "pod": pod,
                "container": container,
                "namespace": namespace
            }
        
        logger.info(f"Found {len(pod_cpu_usage)} pod/container CPU metrics")
        return pod_cpu_usage

    def get_pod_memory_usage_p95(self, lookback_days: int = 7) -> Dict[str, Dict[str, float]]:
        """Get P95 memory usage for all pods over the lookback period."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=lookback_days)
        
        # Query for memory usage by pod
        query = '''
        quantile_over_time(0.95,
            container_memory_working_set_bytes{
                container!="",
                container!="POD",
                namespace="ai-platform"
            }[7d:1h]
        )
        '''
        
        logger.info(f"Querying Memory P95 usage for {lookback_days} days...")
        result = self.prometheus.query_instant(query)
        
        pod_memory_usage = {}
        for metric in result.get("result", []):
            labels = metric.get("metric", {})
            pod = labels.get("pod", "unknown")
            container = labels.get("container", "unknown")
            namespace = labels.get("namespace", "unknown")
            
            value = float(metric.get("value", [0, 0])[1])
            
            key = f"{namespace}/{pod}/{container}"
            if key not in pod_memory_usage:
                pod_memory_usage[key] = {}
            
            pod_memory_usage[key] = {
                "p95_bytes": value,
                "p95_gi": value / (1024 ** 3),
                "pod": pod,
                "container": container,
                "namespace": namespace
            }
        
        logger.info(f"Found {len(pod_memory_usage)} pod/container memory metrics")
        return pod_memory_usage

    def get_current_resource_requests(self) -> Dict[str, Dict[str, Any]]:
        """Get current resource requests/limits from Kubernetes via kube-state-metrics."""
        # CPU requests
        cpu_query = '''
        kube_pod_container_resource_requests{
            resource="cpu",
            namespace="ai-platform"
        }
        '''
        cpu_result = self.prometheus.query_instant(cpu_query)
        
        # Memory requests
        mem_query = '''
        kube_pod_container_resource_requests{
            resource="memory",
            namespace="ai-platform"
        }
        '''
        mem_result = self.prometheus.query_instant(mem_query)
        
        resources = {}
        
        # Process CPU requests
        for metric in cpu_result.get("result", []):
            labels = metric.get("metric", {})
            pod = labels.get("pod", "unknown")
            container = labels.get("container", "unknown")
            namespace = labels.get("namespace", "unknown")
            
            value = float(metric.get("value", [0, 0])[1])
            
            key = f"{namespace}/{pod}/{container}"
            if key not in resources:
                resources[key] = {
                    "pod": pod,
                    "container": container,
                    "namespace": namespace
                }
            
            resources[key]["cpu_request_cores"] = value
        
        # Process memory requests
        for metric in mem_result.get("result", []):
            labels = metric.get("metric", {})
            pod = labels.get("pod", "unknown")
            container = labels.get("container", "container")
            namespace = labels.get("namespace", "unknown")
            
            value = float(metric.get("value", [0, 0])[1])
            
            key = f"{namespace}/{pod}/{container}"
            if key not in resources:
                resources[key] = {
                    "pod": pod,
                    "container": container,
                    "namespace": namespace
                }
            
            resources[key]["memory_request_bytes"] = value
            resources[key]["memory_request_gi"] = value / (1024 ** 3)
        
        logger.info(f"Found {len(resources)} pod/container resource requests")
        return resources

    def generate_recommendations(
        self,
        cpu_usage: Dict[str, Dict[str, float]],
        memory_usage: Dict[str, Dict[str, float]],
        current_requests: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate right-sizing recommendations based on usage data."""
        recommendations = []
        
        # Match pod names (extract base name without random suffix)
        def extract_pod_base_name(pod_name: str) -> str:
            """Extract deployment/statefulset name from pod name."""
            # Remove trailing hash/number patterns
            parts = pod_name.rsplit("-", 2)
            if len(parts) >= 2:
                return "-".join(parts[:-1])
            return pod_name
        
        # Group by workload
        workloads = {}
        for key, request_data in current_requests.items():
            pod_base = extract_pod_base_name(request_data["pod"])
            container = request_data["container"]
            workload_key = f"{request_data['namespace']}/{pod_base}/{container}"
            
            if workload_key not in workloads:
                workloads[workload_key] = {
                    "namespace": request_data["namespace"],
                    "workload": pod_base,
                    "container": container,
                    "pods": []
                }
            
            workloads[workload_key]["pods"].append({
                "key": key,
                "request_data": request_data,
                "cpu_usage": cpu_usage.get(key, {}),
                "memory_usage": memory_usage.get(key, {})
            })
        
        # Generate recommendations per workload
        for workload_key, workload_data in workloads.items():
            namespace = workload_data["namespace"]
            workload = workload_data["workload"]
            container = workload_data["container"]
            
            # Aggregate metrics across all pods in workload
            cpu_p95_values = []
            memory_p95_values = []
            cpu_requests = []
            memory_requests = []
            
            for pod_data in workload_data["pods"]:
                if "p95_cores" in pod_data["cpu_usage"]:
                    cpu_p95_values.append(pod_data["cpu_usage"]["p95_cores"])
                if "p95_bytes" in pod_data["memory_usage"]:
                    memory_p95_values.append(pod_data["memory_usage"]["p95_bytes"])
                if "cpu_request_cores" in pod_data["request_data"]:
                    cpu_requests.append(pod_data["request_data"]["cpu_request_cores"])
                if "memory_request_bytes" in pod_data["request_data"]:
                    memory_requests.append(pod_data["request_data"]["memory_request_bytes"])
            
            if not cpu_p95_values or not cpu_requests:
                continue
            
            # Use max P95 across all pods for safety
            max_cpu_p95 = max(cpu_p95_values)
            max_memory_p95 = max(memory_p95_values) if memory_p95_values else 0
            avg_cpu_request = sum(cpu_requests) / len(cpu_requests)
            avg_memory_request = sum(memory_requests) / len(memory_requests) if memory_requests else 0
            
            recommendation = {
                "namespace": namespace,
                "workload": workload,
                "container": container,
                "current": {
                    "cpu_request_cores": round(avg_cpu_request, 3),
                    "memory_request_gi": round(avg_memory_request / (1024 ** 3), 3)
                },
                "usage": {
                    "cpu_p95_cores": round(max_cpu_p95, 3),
                    "memory_p95_gi": round(max_memory_p95 / (1024 ** 3), 3)
                },
                "utilization": {},
                "recommendation": {},
                "action": "none"
            }
            
            # CPU utilization
            if avg_cpu_request > 0:
                cpu_utilization = max_cpu_p95 / avg_cpu_request
                recommendation["utilization"]["cpu_percent"] = round(cpu_utilization * 100, 1)
                
                if cpu_utilization < self.cpu_underutilization_threshold:
                    # Underutilized - recommend reduction
                    recommended_cpu = max_cpu_p95 * self.cpu_buffer
                    recommendation["recommendation"]["cpu_request_cores"] = round(recommended_cpu, 3)
                    recommendation["action"] = "reduce_cpu"
                    recommendation["potential_savings"] = {
                        "cpu_cores": round(avg_cpu_request - recommended_cpu, 3)
                    }
                elif cpu_utilization > self.cpu_overutilization_threshold:
                    # Overutilized - recommend increase
                    recommended_cpu = max_cpu_p95 * self.cpu_buffer
                    recommendation["recommendation"]["cpu_request_cores"] = round(recommended_cpu, 3)
                    recommendation["action"] = "increase_cpu"
                    recommendation["risk"] = "high_cpu_utilization"
            
            # Memory utilization
            if avg_memory_request > 0:
                memory_utilization = max_memory_p95 / avg_memory_request
                recommendation["utilization"]["memory_percent"] = round(memory_utilization * 100, 1)
                
                if memory_utilization < self.memory_underutilization_threshold:
                    # Underutilized - recommend reduction
                    recommended_memory = max_memory_p95 * self.memory_buffer
                    recommendation["recommendation"]["memory_request_gi"] = round(
                        recommended_memory / (1024 ** 3), 3
                    )
                    if recommendation["action"] == "none":
                        recommendation["action"] = "reduce_memory"
                    elif recommendation["action"] == "reduce_cpu":
                        recommendation["action"] = "reduce_both"
                    
                    recommendation["potential_savings"]["memory_gi"] = round(
                        (avg_memory_request - recommended_memory) / (1024 ** 3), 3
                    )
                elif memory_utilization > self.memory_overutilization_threshold:
                    # Overutilized - recommend increase
                    recommended_memory = max_memory_p95 * self.memory_buffer
                    recommendation["recommendation"]["memory_request_gi"] = round(
                        recommended_memory / (1024 ** 3), 3
                    )
                    if recommendation["action"] == "none":
                        recommendation["action"] = "increase_memory"
                    elif recommendation["action"] == "increase_cpu":
                        recommendation["action"] = "increase_both"
                    recommendation["risk"] = "high_memory_utilization"
            
            recommendations.append(recommendation)
        
        # Sort by potential savings (CPU + memory)
        recommendations.sort(
            key=lambda r: (
                r.get("potential_savings", {}).get("cpu_cores", 0) +
                r.get("potential_savings", {}).get("memory_gi", 0)
            ),
            reverse=True
        )
        
        return recommendations

    def estimate_cost_savings(self, recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Estimate monthly cost savings from recommendations."""
        # Average cloud pricing (USD/month)
        cpu_core_cost = 30.0  # ~$30/month per CPU core
        memory_gb_cost = 4.0   # ~$4/month per GB memory
        
        total_cpu_savings = 0.0
        total_memory_savings = 0.0
        
        for rec in recommendations:
            savings = rec.get("potential_savings", {})
            total_cpu_savings += savings.get("cpu_cores", 0)
            total_memory_savings += savings.get("memory_gi", 0)
        
        monthly_savings = (
            total_cpu_savings * cpu_core_cost +
            total_memory_savings * memory_gb_cost
        )
        annual_savings = monthly_savings * 12
        
        return {
            "total_cpu_cores_saved": round(total_cpu_savings, 2),
            "total_memory_gi_saved": round(total_memory_savings, 2),
            "estimated_monthly_savings_usd": round(monthly_savings, 2),
            "estimated_annual_savings_usd": round(annual_savings, 2)
        }


def main():
    """Main entry point."""
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
    output_file = os.getenv("OUTPUT_FILE", "resource_recommendations.json")
    lookback_days = int(os.getenv("LOOKBACK_DAYS", "7"))
    
    logger.info("=" * 80)
    logger.info("Resource Usage Analyzer - Cost Optimization Report")
    logger.info("=" * 80)
    logger.info(f"Prometheus URL: {prometheus_url}")
    logger.info(f"Lookback period: {lookback_days} days")
    logger.info(f"Output file: {output_file}")
    logger.info("")
    
    try:
        # Initialize clients
        prom_client = PrometheusClient(prometheus_url)
        analyzer = ResourceAnalyzer(prom_client)
        
        # Gather metrics
        logger.info("Step 1: Gathering CPU usage metrics...")
        cpu_usage = analyzer.get_pod_cpu_usage_p95(lookback_days)
        
        logger.info("Step 2: Gathering memory usage metrics...")
        memory_usage = analyzer.get_pod_memory_usage_p95(lookback_days)
        
        logger.info("Step 3: Gathering current resource requests...")
        current_requests = analyzer.get_current_resource_requests()
        
        logger.info("Step 4: Generating right-sizing recommendations...")
        recommendations = analyzer.generate_recommendations(
            cpu_usage,
            memory_usage,
            current_requests
        )
        
        logger.info("Step 5: Estimating cost savings...")
        cost_savings = analyzer.estimate_cost_savings(recommendations)
        
        # Generate report
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "lookback_days": lookback_days,
            "summary": {
                "total_workloads_analyzed": len(current_requests),
                "recommendations_generated": len(recommendations),
                "cost_savings": cost_savings
            },
            "recommendations": recommendations
        }
        
        # Write to file
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info("")
        logger.info("=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total workloads analyzed: {report['summary']['total_workloads_analyzed']}")
        logger.info(f"Recommendations generated: {report['summary']['recommendations_generated']}")
        logger.info("")
        logger.info("Cost Savings Potential:")
        logger.info(f"  CPU cores saved: {cost_savings['total_cpu_cores_saved']}")
        logger.info(f"  Memory (Gi) saved: {cost_savings['total_memory_gi_saved']}")
        logger.info(f"  Estimated monthly savings: ${cost_savings['estimated_monthly_savings_usd']}")
        logger.info(f"  Estimated annual savings: ${cost_savings['estimated_annual_savings_usd']}")
        logger.info("")
        logger.info(f"Full report written to: {output_file}")
        logger.info("=" * 80)
        
        # Print top recommendations
        if recommendations:
            logger.info("")
            logger.info("Top 5 Right-Sizing Recommendations:")
            logger.info("-" * 80)
            for i, rec in enumerate(recommendations[:5], 1):
                logger.info(f"{i}. {rec['workload']} ({rec['container']})")
                logger.info(f"   Action: {rec['action']}")
                logger.info(f"   Current: CPU={rec['current'].get('cpu_request_cores', 0)} cores, "
                          f"Memory={rec['current'].get('memory_request_gi', 0)} Gi")
                logger.info(f"   Usage (P95): CPU={rec['usage'].get('cpu_p95_cores', 0)} cores, "
                          f"Memory={rec['usage'].get('memory_p95_gi', 0)} Gi")
                if rec.get('recommendation'):
                    logger.info(f"   Recommended: CPU={rec['recommendation'].get('cpu_request_cores', 'N/A')} cores, "
                              f"Memory={rec['recommendation'].get('memory_request_gi', 'N/A')} Gi")
                logger.info("")
        
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
