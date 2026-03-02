#!/usr/bin/env python3
"""
Apply resource right-sizing recommendations to Kubernetes deployments.

Reads recommendations from analyze_resource_usage.py output and applies them
to Helm values or directly patches Kubernetes deployments.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, List, Any
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class RecommendationApplier:
    """Applies resource right-sizing recommendations."""

    def __init__(self, recommendations_file: str, dry_run: bool = True):
        """
        Initialize the applier.

        Args:
            recommendations_file: Path to recommendations JSON file
            dry_run: If True, only show what would be changed
        """
        self.recommendations_file = recommendations_file
        self.dry_run = dry_run
        self.recommendations = self._load_recommendations()

    def _load_recommendations(self) -> List[Dict[str, Any]]:
        """Load recommendations from JSON file."""
        with open(self.recommendations_file, 'r') as f:
            data = json.load(f)
        
        recommendations = data.get("recommendations", [])
        logger.info(f"Loaded {len(recommendations)} recommendations")
        return recommendations

    def generate_helm_values_patch(self) -> Dict[str, Any]:
        """
        Generate Helm values patch for recommendations.

        Returns:
            Dictionary with Helm values structure
        """
        values_patch = {}
        
        # Map workload names to Helm values paths
        workload_mappings = {
            "api-server": "apiServer.resources",
            "gateway": "gateway.resources",
            "mcpjungle": "mcpjungle.resources",
            "mem0": "mem0.resources",
            "learning-engine": "learningEngine.resources",
            "maml-service": "mamlService.resources",
            "grafana": "grafana.resources",
            "prometheus": "prometheus.resources",
            "jaeger": "jaeger.resources",
            "qdrant": "qdrant.resources",
            "redis": "redis.resources",
            "postgres": "postgres.resources",
            "neo4j": "neo4j.resources",
            "minio": "minio.resources",
        }
        
        for rec in self.recommendations:
            workload = rec.get("workload", "")
            action = rec.get("action", "")
            
            # Skip non-actionable recommendations
            if action == "none" or not rec.get("recommendation"):
                continue
            
            # Find matching workload mapping
            values_path = None
            for workload_key, path in workload_mappings.items():
                if workload_key in workload.lower():
                    values_path = path
                    break
            
            if not values_path:
                logger.warning(f"No Helm mapping found for workload: {workload}")
                continue
            
            # Build resource values
            resources = {
                "requests": {}
            }
            
            recommendation = rec.get("recommendation", {})
            if "cpu_request_cores" in recommendation:
                cpu_cores = recommendation["cpu_request_cores"]
                # Convert to Kubernetes format (e.g., 0.5 -> "500m", 2.0 -> "2")
                if cpu_cores < 1.0:
                    cpu_str = f"{int(cpu_cores * 1000)}m"
                else:
                    cpu_str = str(int(cpu_cores))
                resources["requests"]["cpu"] = cpu_str
            
            if "memory_request_gi" in recommendation:
                memory_gi = recommendation["memory_request_gi"]
                # Convert to Kubernetes format (e.g., 1.5 -> "1536Mi", 2.0 -> "2Gi")
                if memory_gi < 1.0:
                    memory_str = f"{int(memory_gi * 1024)}Mi"
                else:
                    memory_str = f"{memory_gi}Gi"
                resources["requests"]["memory"] = memory_str
            
            # Set resource path in values_patch
            path_parts = values_path.split(".")
            current = values_patch
            for part in path_parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[path_parts[-1]] = resources
            
            logger.info(f"Generated patch for {workload}: {values_path} = {resources}")
        
        return values_patch

    def write_helm_values_patch(self, output_file: str):
        """
        Write Helm values patch to YAML file.

        Args:
            output_file: Path to output YAML file
        """
        values_patch = self.generate_helm_values_patch()
        
        if not values_patch:
            logger.warning("No actionable recommendations to apply")
            return
        
        with open(output_file, 'w') as f:
            yaml.dump(values_patch, f, default_flow_style=False)
        
        logger.info(f"Wrote Helm values patch to: {output_file}")
        
        # Print usage instructions
        logger.info("")
        logger.info("To apply these recommendations:")
        logger.info(f"  helm upgrade ai-platform ./helm/ai-platform -f {output_file}")
        logger.info("")

    def print_summary(self):
        """Print summary of recommendations."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("RECOMMENDATIONS SUMMARY")
        logger.info("=" * 80)
        
        actions = {}
        total_savings = {
            "cpu_cores": 0.0,
            "memory_gi": 0.0
        }
        
        for rec in self.recommendations:
            action = rec.get("action", "none")
            actions[action] = actions.get(action, 0) + 1
            
            savings = rec.get("potential_savings", {})
            total_savings["cpu_cores"] += savings.get("cpu_cores", 0)
            total_savings["memory_gi"] += savings.get("memory_gi", 0)
        
        logger.info("")
        logger.info("Actions:")
        for action, count in sorted(actions.items()):
            logger.info(f"  {action}: {count}")
        
        logger.info("")
        logger.info("Potential Savings:")
        logger.info(f"  CPU: {total_savings['cpu_cores']:.2f} cores")
        logger.info(f"  Memory: {total_savings['memory_gi']:.2f} Gi")
        
        # Estimate cost savings (same as analyzer)
        cpu_core_cost = 30.0  # $30/month per CPU core
        memory_gb_cost = 4.0   # $4/month per GB memory
        
        monthly_savings = (
            total_savings["cpu_cores"] * cpu_core_cost +
            total_savings["memory_gi"] * memory_gb_cost
        )
        annual_savings = monthly_savings * 12
        
        logger.info(f"  Estimated monthly: ${monthly_savings:.2f}")
        logger.info(f"  Estimated annual: ${annual_savings:.2f}")
        logger.info("")
        logger.info("=" * 80)

    def apply_recommendations_interactive(self):
        """Interactively apply recommendations."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("INTERACTIVE RECOMMENDATION APPLICATION")
        logger.info("=" * 80)
        logger.info("")
        
        for i, rec in enumerate(self.recommendations, 1):
            if rec.get("action") == "none":
                continue
            
            logger.info(f"Recommendation {i}:")
            logger.info(f"  Workload: {rec['workload']} ({rec['container']})")
            logger.info(f"  Namespace: {rec['namespace']}")
            logger.info(f"  Action: {rec['action']}")
            logger.info("")
            logger.info("  Current:")
            logger.info(f"    CPU: {rec['current'].get('cpu_request_cores', 'N/A')} cores")
            logger.info(f"    Memory: {rec['current'].get('memory_request_gi', 'N/A')} Gi")
            logger.info("")
            logger.info("  Recommended:")
            logger.info(f"    CPU: {rec['recommendation'].get('cpu_request_cores', 'N/A')} cores")
            logger.info(f"    Memory: {rec['recommendation'].get('memory_request_gi', 'N/A')} Gi")
            logger.info("")
            logger.info("  Utilization:")
            logger.info(f"    CPU: {rec['utilization'].get('cpu_percent', 'N/A')}%")
            logger.info(f"    Memory: {rec['utilization'].get('memory_percent', 'N/A')}%")
            
            if rec.get("potential_savings"):
                logger.info("")
                logger.info("  Savings:")
                logger.info(f"    CPU: {rec['potential_savings'].get('cpu_cores', 0):.3f} cores")
                logger.info(f"    Memory: {rec['potential_savings'].get('memory_gi', 0):.3f} Gi")
            
            logger.info("")
            logger.info("-" * 80)
            logger.info("")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apply resource right-sizing recommendations"
    )
    parser.add_argument(
        "recommendations_file",
        help="Path to recommendations JSON file"
    )
    parser.add_argument(
        "-o", "--output",
        default="helm-values-patch.yaml",
        help="Output Helm values patch file (default: helm-values-patch.yaml)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry run mode (default: true)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode: review each recommendation"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print summary only, don't generate patches"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.recommendations_file):
        logger.error(f"Recommendations file not found: {args.recommendations_file}")
        return 1
    
    try:
        applier = RecommendationApplier(
            recommendations_file=args.recommendations_file,
            dry_run=args.dry_run
        )
        
        if args.summary:
            applier.print_summary()
        elif args.interactive:
            applier.apply_recommendations_interactive()
            applier.print_summary()
        else:
            applier.write_helm_values_patch(args.output)
            applier.print_summary()
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to apply recommendations: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
