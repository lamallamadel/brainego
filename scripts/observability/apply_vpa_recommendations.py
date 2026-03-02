#!/usr/bin/env python3
"""
VPA Recommendations Applier for Kubernetes cluster cost optimization.

Reads analyze_resource_usage.py output, generates VPA manifests with:
- updateMode=Auto for non-critical services (api-server, gateway, mcpjungle)
- updateMode=Initial for StatefulSets (redis, qdrant, postgres, neo4j, minio)
- Dry-run mode for testing
- Validates resource changes within 50% delta to prevent thrashing
- Integrates with Grafana cost dashboard for savings tracking
"""

import os
import sys
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

# Needs: python-package:pyyaml>=6.0
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class VPAManifestGenerator:
    """Generates VPA manifests from right-sizing recommendations."""
    
    # Services that can use updateMode=Auto (safe to restart)
    NON_CRITICAL_SERVICES = {
        "api-server",
        "gateway",
        "mcpjungle",
        "mem0",
        "grafana",
        "jaeger",
        "prometheus",
        "alertmanager",
        "agent-router",
        "learning-engine",
        "maml-service",
        "max-serve-llama",
        "max-serve-qwen",
        "max-serve-deepseek"
    }
    
    # StatefulSets that should use updateMode=Initial (no automatic restarts)
    STATEFUL_SERVICES = {
        "redis",
        "qdrant",
        "postgres",
        "neo4j",
        "minio"
    }
    
    # Maximum allowed resource change percentage to prevent thrashing
    MAX_CHANGE_PERCENT = 0.50  # 50%
    
    def __init__(self, namespace: str = "ai-platform", dry_run: bool = False):
        self.namespace = namespace
        self.dry_run = dry_run
        self.vpas = []
        self.validation_errors = []
        self.applied_recommendations = []
        
    def parse_kubernetes_resource(self, value: str) -> float:
        """Parse Kubernetes resource string to numeric value."""
        if not value:
            return 0.0
            
        value = str(value).strip()
        
        # Handle CPU millicores
        if value.endswith('m'):
            return float(value[:-1]) / 1000.0
        
        # Handle memory units
        if value.endswith('Ki'):
            return float(value[:-2]) / (1024 ** 2)  # Convert to Gi
        elif value.endswith('Mi'):
            return float(value[:-2]) / 1024  # Convert to Gi
        elif value.endswith('Gi'):
            return float(value[:-2])
        elif value.endswith('Ti'):
            return float(value[:-2]) * 1024
        
        # Assume it's already in base units
        try:
            return float(value)
        except ValueError:
            logger.warning(f"Could not parse resource value: {value}")
            return 0.0
    
    def format_cpu_resource(self, cores: float) -> str:
        """Format CPU cores as Kubernetes resource string."""
        if cores < 0.01:
            return f"{int(cores * 1000)}m"
        elif cores < 1.0:
            # Use millicores for fractional values
            return f"{int(cores * 1000)}m"
        else:
            return str(int(cores)) if cores == int(cores) else str(cores)
    
    def format_memory_resource(self, gi: float) -> str:
        """Format memory Gi as Kubernetes resource string."""
        if gi < 0.001:
            return f"{int(gi * 1024 * 1024)}Ki"
        elif gi < 1.0:
            return f"{int(gi * 1024)}Mi"
        else:
            return f"{gi}Gi"
    
    def validate_resource_change(
        self,
        current: float,
        recommended: float,
        resource_type: str
    ) -> bool:
        """Validate that resource change is within acceptable bounds."""
        if current == 0:
            # No current value, accept recommendation
            return True
        
        change_ratio = abs(recommended - current) / current
        
        if change_ratio > self.MAX_CHANGE_PERCENT:
            self.validation_errors.append({
                "resource_type": resource_type,
                "current": current,
                "recommended": recommended,
                "change_percent": round(change_ratio * 100, 1),
                "reason": f"Change exceeds {self.MAX_CHANGE_PERCENT * 100}% threshold"
            })
            return False
        
        return True
    
    def determine_update_mode(self, workload_name: str) -> str:
        """Determine VPA updateMode based on workload type."""
        # Extract base workload name (remove trailing numbers/hashes)
        base_name = workload_name.rsplit('-', 1)[0] if '-' in workload_name else workload_name
        
        if base_name in self.STATEFUL_SERVICES:
            return "Initial"
        elif base_name in self.NON_CRITICAL_SERVICES:
            return "Auto"
        else:
            # Default to Initial for unknown services (safer)
            logger.warning(f"Unknown service type: {workload_name}, defaulting to Initial mode")
            return "Initial"
    
    def determine_workload_kind(self, workload_name: str) -> str:
        """Determine Kubernetes workload kind (Deployment or StatefulSet)."""
        base_name = workload_name.rsplit('-', 1)[0] if '-' in workload_name else workload_name
        
        if base_name in self.STATEFUL_SERVICES:
            return "StatefulSet"
        else:
            return "Deployment"
    
    def generate_vpa_manifest(
        self,
        recommendation: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Generate a single VPA manifest from a recommendation."""
        workload = recommendation.get("workload")
        container = recommendation.get("container")
        namespace = recommendation.get("namespace", self.namespace)
        
        if not workload or not container:
            logger.warning("Skipping recommendation without workload or container name")
            return None
        
        # Get current and recommended resources
        current = recommendation.get("current", {})
        recommended = recommendation.get("recommendation", {})
        
        if not recommended:
            logger.info(f"No recommendations for {workload}/{container}, skipping")
            return None
        
        # Validate resource changes
        cpu_current = current.get("cpu_request_cores", 0)
        cpu_recommended = recommended.get("cpu_request_cores", 0)
        memory_current = current.get("memory_request_gi", 0)
        memory_recommended = recommended.get("memory_request_gi", 0)
        
        # Apply validation
        valid_cpu = True
        valid_memory = True
        
        if cpu_recommended > 0:
            valid_cpu = self.validate_resource_change(
                cpu_current,
                cpu_recommended,
                f"{workload}/cpu"
            )
        
        if memory_recommended > 0:
            valid_memory = self.validate_resource_change(
                memory_current,
                memory_recommended,
                f"{workload}/memory"
            )
        
        if not valid_cpu or not valid_memory:
            logger.warning(
                f"Skipping {workload}/{container} due to validation failure "
                f"(change exceeds {self.MAX_CHANGE_PERCENT * 100}%)"
            )
            return None
        
        # Determine update mode and workload kind
        update_mode = self.determine_update_mode(workload)
        workload_kind = self.determine_workload_kind(workload)
        
        # Calculate min/max bounds (±30% from recommended for safety)
        min_cpu = self.format_cpu_resource(cpu_recommended * 0.7) if cpu_recommended > 0 else "100m"
        max_cpu = self.format_cpu_resource(cpu_recommended * 1.3) if cpu_recommended > 0 else "4"
        min_memory = self.format_memory_resource(memory_recommended * 0.7) if memory_recommended > 0 else "256Mi"
        max_memory = self.format_memory_resource(memory_recommended * 1.3) if memory_recommended > 0 else "8Gi"
        
        # Build VPA manifest
        vpa = {
            "apiVersion": "autoscaling.k8s.io/v1",
            "kind": "VerticalPodAutoscaler",
            "metadata": {
                "name": f"{workload}-vpa",
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/name": workload,
                    "app.kubernetes.io/component": "vpa",
                    "app.kubernetes.io/managed-by": "vpa-automation",
                    "generated-by": "apply_vpa_recommendations.py",
                    "generated-at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                },
                "annotations": {
                    "vpa.automation/source": "analyze_resource_usage.py",
                    "vpa.automation/dry-run": str(self.dry_run).lower(),
                    "vpa.automation/cpu-current": f"{cpu_current}",
                    "vpa.automation/cpu-recommended": f"{cpu_recommended}",
                    "vpa.automation/memory-current-gi": f"{memory_current}",
                    "vpa.automation/memory-recommended-gi": f"{memory_recommended}"
                }
            },
            "spec": {
                "targetRef": {
                    "apiVersion": "apps/v1",
                    "kind": workload_kind,
                    "name": workload
                },
                "updatePolicy": {
                    "updateMode": update_mode
                },
                "resourcePolicy": {
                    "containerPolicies": [
                        {
                            "containerName": container,
                            "minAllowed": {
                                "cpu": min_cpu,
                                "memory": min_memory
                            },
                            "maxAllowed": {
                                "cpu": max_cpu,
                                "memory": max_memory
                            },
                            "controlledResources": ["cpu", "memory"]
                        }
                    ]
                }
            }
        }
        
        # Track applied recommendation
        self.applied_recommendations.append({
            "workload": workload,
            "container": container,
            "update_mode": update_mode,
            "workload_kind": workload_kind,
            "resources": {
                "cpu": {
                    "current_cores": cpu_current,
                    "recommended_cores": cpu_recommended,
                    "min": min_cpu,
                    "max": max_cpu,
                    "change_percent": round((cpu_recommended - cpu_current) / cpu_current * 100, 1) if cpu_current > 0 else 0
                },
                "memory": {
                    "current_gi": memory_current,
                    "recommended_gi": memory_recommended,
                    "min": min_memory,
                    "max": max_memory,
                    "change_percent": round((memory_recommended - memory_current) / memory_current * 100, 1) if memory_current > 0 else 0
                }
            },
            "potential_savings": recommendation.get("potential_savings", {})
        })
        
        return vpa
    
    def generate_all_vpas(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate VPA manifests for all recommendations."""
        logger.info(f"Generating VPA manifests for {len(recommendations)} recommendations...")
        
        for rec in recommendations:
            vpa = self.generate_vpa_manifest(rec)
            if vpa:
                self.vpas.append(vpa)
        
        logger.info(f"Generated {len(self.vpas)} VPA manifests")
        
        if self.validation_errors:
            logger.warning(f"Skipped {len(self.validation_errors)} recommendations due to validation errors")
            for error in self.validation_errors[:5]:  # Show first 5
                logger.warning(
                    f"  - {error['resource_type']}: "
                    f"current={error['current']:.3f}, "
                    f"recommended={error['recommended']:.3f}, "
                    f"change={error['change_percent']}%"
                )
        
        return self.vpas
    
    def write_helm_template(self, output_path: str):
        """Write VPA manifests as Helm template."""
        logger.info(f"Writing VPA manifests to {output_path}...")
        
        # Generate Helm template with conditional logic
        helm_template = self._generate_helm_template()
        
        with open(output_path, 'w') as f:
            f.write(helm_template)
        
        logger.info(f"Successfully wrote {len(self.vpas)} VPA manifests to {output_path}")
    
    def _generate_helm_template(self) -> str:
        """Generate Helm template with all VPAs."""
        lines = [
            "{{- if .Values.vpa.enabled -}}",
            "# VPA Manifests - Auto-generated by apply_vpa_recommendations.py",
            f"# Generated at: {datetime.utcnow().isoformat()}Z",
            f"# Total VPAs: {len(self.vpas)}",
            "# DO NOT EDIT MANUALLY - Changes will be overwritten",
            ""
        ]
        
        for i, vpa in enumerate(self.vpas):
            if i > 0:
                lines.append("---")
            
            # Convert VPA to YAML and add Helm templating
            vpa_yaml = yaml.dump(vpa, default_flow_style=False, sort_keys=False)
            
            # Add Helm value overrides for key parameters
            workload = vpa["metadata"]["labels"]["app.kubernetes.io/name"]
            update_mode = vpa["spec"]["updatePolicy"]["updateMode"]
            
            # Add comments
            lines.append(f"# VPA for {workload} (updateMode: {update_mode})")
            
            # Replace namespace with Helm template
            vpa_yaml = vpa_yaml.replace(
                f'namespace: {self.namespace}',
                'namespace: {{ .Values.namespace.name }}'
            )
            
            # Add updateMode override capability
            vpa_yaml = vpa_yaml.replace(
                f'updateMode: {update_mode}',
                f'updateMode: {{{{ .Values.vpa.{workload}.updateMode | default "{update_mode}" }}}}'
            )
            
            lines.append(vpa_yaml)
        
        lines.append("{{- end }}")
        
        return "\n".join(lines)
    
    def write_raw_manifests(self, output_dir: str):
        """Write VPA manifests as standalone Kubernetes YAML files."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Writing {len(self.vpas)} raw VPA manifests to {output_dir}...")
        
        for vpa in self.vpas:
            workload = vpa["metadata"]["labels"]["app.kubernetes.io/name"]
            filename = f"{workload}-vpa.yaml"
            filepath = output_path / filename
            
            with open(filepath, 'w') as f:
                yaml.dump(vpa, f, default_flow_style=False, sort_keys=False)
            
            logger.debug(f"  Wrote {filename}")
        
        logger.info(f"Successfully wrote {len(self.vpas)} VPA manifests to {output_dir}")
    
    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate summary report of VPA application."""
        total_cpu_savings = sum(
            rec.get("potential_savings", {}).get("cpu_cores", 0)
            for rec in self.applied_recommendations
        )
        
        total_memory_savings = sum(
            rec.get("potential_savings", {}).get("memory_gi", 0)
            for rec in self.applied_recommendations
        )
        
        # Cost calculations (approximate)
        cpu_core_cost = 30.0  # USD/month
        memory_gb_cost = 4.0  # USD/month
        
        monthly_savings = (
            total_cpu_savings * cpu_core_cost +
            total_memory_savings * memory_gb_cost
        )
        
        return {
            "summary": {
                "total_vpas_generated": len(self.vpas),
                "total_recommendations_processed": len(self.applied_recommendations),
                "validation_errors": len(self.validation_errors),
                "dry_run_mode": self.dry_run,
                "namespace": self.namespace
            },
            "update_modes": {
                "auto": len([r for r in self.applied_recommendations if r["update_mode"] == "Auto"]),
                "initial": len([r for r in self.applied_recommendations if r["update_mode"] == "Initial"])
            },
            "cost_savings": {
                "total_cpu_cores_saved": round(total_cpu_savings, 3),
                "total_memory_gi_saved": round(total_memory_savings, 3),
                "estimated_monthly_savings_usd": round(monthly_savings, 2),
                "estimated_annual_savings_usd": round(monthly_savings * 12, 2)
            },
            "applied_recommendations": self.applied_recommendations,
            "validation_errors": self.validation_errors
        }


class GrafanaDashboardUpdater:
    """Updates Grafana cost dashboard with VPA savings metrics."""
    
    def __init__(self, dashboard_path: str):
        self.dashboard_path = dashboard_path
        self.dashboard = None
    
    def load_dashboard(self):
        """Load existing Grafana dashboard."""
        with open(self.dashboard_path, 'r') as f:
            self.dashboard = json.load(f)
        logger.info(f"Loaded Grafana dashboard from {self.dashboard_path}")
    
    def add_vpa_savings_panel(self, summary: Dict[str, Any]):
        """Add VPA savings panel to cost dashboard."""
        if not self.dashboard:
            self.load_dashboard()
        
        # Find next available panel ID and position
        panels = self.dashboard.get("panels", [])
        max_id = max([p.get("id", 0) for p in panels] or [0])
        next_id = max_id + 1
        
        # Calculate grid position (append to bottom)
        max_y = max([p.get("gridPos", {}).get("y", 0) + p.get("gridPos", {}).get("h", 0) for p in panels] or [0])
        
        # Create VPA Savings stat panel
        vpa_savings_panel = {
            "datasource": {
                "type": "prometheus",
                "uid": "prometheus"
            },
            "fieldConfig": {
                "defaults": {
                    "color": {
                        "mode": "thresholds"
                    },
                    "mappings": [],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "yellow", "value": 500},
                            {"color": "red", "value": 1000}
                        ]
                    },
                    "unit": "currencyUSD"
                },
                "overrides": []
            },
            "gridPos": {
                "h": 6,
                "w": 6,
                "x": 0,
                "y": max_y
            },
            "id": next_id,
            "options": {
                "colorMode": "value",
                "graphMode": "area",
                "justifyMode": "auto",
                "orientation": "auto",
                "reduceOptions": {
                    "values": False,
                    "calcs": ["lastNotNull"],
                    "fields": ""
                },
                "textMode": "auto"
            },
            "pluginVersion": "10.2.2",
            "targets": [
                {
                    "datasource": {
                        "type": "prometheus",
                        "uid": "prometheus"
                    },
                    "editorMode": "code",
                    "expr": f"vector({summary['cost_savings']['estimated_monthly_savings_usd']})",
                    "legendFormat": "VPA Potential Savings",
                    "range": True,
                    "refId": "A"
                }
            ],
            "title": "VPA Potential Monthly Savings",
            "type": "stat",
            "description": f"Estimated monthly cost savings from VPA recommendations. Based on {summary['summary']['total_vpas_generated']} VPA configurations."
        }
        
        # Create VPA resource optimization table
        vpa_table_panel = {
            "datasource": {
                "type": "prometheus",
                "uid": "prometheus"
            },
            "fieldConfig": {
                "defaults": {
                    "color": {
                        "mode": "thresholds"
                    },
                    "custom": {
                        "align": "left",
                        "cellOptions": {"type": "auto"},
                        "inspect": False
                    },
                    "mappings": [],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [{"color": "green", "value": None}]
                    }
                },
                "overrides": []
            },
            "gridPos": {
                "h": 6,
                "w": 18,
                "x": 6,
                "y": max_y
            },
            "id": next_id + 1,
            "options": {
                "cellHeight": "sm",
                "footer": {
                    "countRows": False,
                    "fields": "",
                    "reducer": ["sum"],
                    "show": True
                },
                "showHeader": True
            },
            "pluginVersion": "10.2.2",
            "targets": [
                {
                    "datasource": {
                        "type": "prometheus",
                        "uid": "prometheus"
                    },
                    "editorMode": "code",
                    "expr": "sum by (pod) (kube_pod_container_resource_requests{namespace=\"ai-platform\", resource=\"cpu\"})",
                    "format": "table",
                    "legendFormat": "{{pod}}",
                    "range": True,
                    "refId": "A"
                }
            ],
            "title": "VPA-Managed Resource Requests",
            "type": "table",
            "description": f"Current resource requests for pods managed by VPA. Total VPAs active: {summary['summary']['total_vpas_generated']}"
        }
        
        # Add panels to dashboard
        self.dashboard["panels"].extend([vpa_savings_panel, vpa_table_panel])
        
        logger.info(f"Added 2 VPA savings panels to dashboard (IDs: {next_id}, {next_id + 1})")
    
    def save_dashboard(self):
        """Save updated Grafana dashboard."""
        with open(self.dashboard_path, 'w') as f:
            json.dump(self.dashboard, f, indent=2)
        logger.info(f"Saved updated Grafana dashboard to {self.dashboard_path}")


def main():
    """Main entry point."""
    # Parse arguments
    input_file = os.getenv("INPUT_FILE", "resource_recommendations.json")
    output_helm_template = os.getenv("OUTPUT_HELM_TEMPLATE", "helm/ai-platform/templates/vpa.yaml")
    output_raw_dir = os.getenv("OUTPUT_RAW_DIR", "manifests/vpa")
    grafana_dashboard = os.getenv("GRAFANA_DASHBOARD", "configs/grafana/dashboards/cost-optimization.json")
    namespace = os.getenv("NAMESPACE", "ai-platform")
    dry_run = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")
    summary_output = os.getenv("SUMMARY_OUTPUT", "vpa_application_summary.json")
    
    logger.info("=" * 80)
    logger.info("VPA Recommendations Applier")
    logger.info("=" * 80)
    logger.info(f"Input file: {input_file}")
    logger.info(f"Output Helm template: {output_helm_template}")
    logger.info(f"Output raw manifests: {output_raw_dir}")
    logger.info(f"Grafana dashboard: {grafana_dashboard}")
    logger.info(f"Namespace: {namespace}")
    logger.info(f"Dry-run mode: {dry_run}")
    logger.info("")
    
    try:
        # Load recommendations
        logger.info("Step 1: Loading resource recommendations...")
        with open(input_file, 'r') as f:
            data = json.load(f)
        
        recommendations = data.get("recommendations", [])
        logger.info(f"Loaded {len(recommendations)} recommendations")
        
        # Initialize VPA generator
        generator = VPAManifestGenerator(namespace=namespace, dry_run=dry_run)
        
        # Generate VPA manifests
        logger.info("Step 2: Generating VPA manifests...")
        vpas = generator.generate_all_vpas(recommendations)
        
        if not vpas:
            logger.warning("No VPA manifests generated. Exiting.")
            return 1
        
        # Write Helm template
        logger.info("Step 3: Writing Helm template...")
        generator.write_helm_template(output_helm_template)
        
        # Write raw manifests (for kubectl apply)
        logger.info("Step 4: Writing raw manifests...")
        generator.write_raw_manifests(output_raw_dir)
        
        # Generate summary report
        logger.info("Step 5: Generating summary report...")
        summary = generator.generate_summary_report()
        
        with open(summary_output, 'w') as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Summary report written to {summary_output}")
        
        # Update Grafana dashboard
        logger.info("Step 6: Updating Grafana cost dashboard...")
        try:
            dashboard_updater = GrafanaDashboardUpdater(grafana_dashboard)
            dashboard_updater.load_dashboard()
            dashboard_updater.add_vpa_savings_panel(summary)
            dashboard_updater.save_dashboard()
        except Exception as e:
            logger.warning(f"Failed to update Grafana dashboard: {e}")
            logger.warning("Continuing without dashboard update...")
        
        # Print summary
        logger.info("")
        logger.info("=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total VPAs generated: {summary['summary']['total_vpas_generated']}")
        logger.info(f"Update modes:")
        logger.info(f"  - Auto (non-critical): {summary['update_modes']['auto']}")
        logger.info(f"  - Initial (StatefulSets): {summary['update_modes']['initial']}")
        logger.info(f"Validation errors: {summary['summary']['validation_errors']}")
        logger.info("")
        logger.info("Cost Savings Potential:")
        logger.info(f"  CPU cores saved: {summary['cost_savings']['total_cpu_cores_saved']}")
        logger.info(f"  Memory (Gi) saved: {summary['cost_savings']['total_memory_gi_saved']}")
        logger.info(f"  Estimated monthly savings: ${summary['cost_savings']['estimated_monthly_savings_usd']}")
        logger.info(f"  Estimated annual savings: ${summary['cost_savings']['estimated_annual_savings_usd']}")
        logger.info("")
        
        if dry_run:
            logger.info("DRY RUN MODE - No changes applied to cluster")
            logger.info("To apply changes, run with DRY_RUN=false")
        else:
            logger.info("VPA manifests ready for application:")
            logger.info(f"  Helm: helm upgrade ai-platform {Path(output_helm_template).parent.parent}")
            logger.info(f"  kubectl: kubectl apply -f {output_raw_dir}/")
        
        logger.info("=" * 80)
        
        # Print top recommendations
        if summary["applied_recommendations"]:
            logger.info("")
            logger.info("Top 5 Applied VPA Recommendations:")
            logger.info("-" * 80)
            
            # Sort by savings
            sorted_recs = sorted(
                summary["applied_recommendations"],
                key=lambda r: (
                    r.get("potential_savings", {}).get("cpu_cores", 0) +
                    r.get("potential_savings", {}).get("memory_gi", 0)
                ),
                reverse=True
            )
            
            for i, rec in enumerate(sorted_recs[:5], 1):
                logger.info(f"{i}. {rec['workload']} ({rec['container']})")
                logger.info(f"   Mode: {rec['update_mode']} ({rec['workload_kind']})")
                logger.info(f"   CPU: {rec['resources']['cpu']['current_cores']:.3f} → "
                          f"{rec['resources']['cpu']['recommended_cores']:.3f} cores "
                          f"({rec['resources']['cpu']['change_percent']:+.1f}%)")
                logger.info(f"   Memory: {rec['resources']['memory']['current_gi']:.3f} → "
                          f"{rec['resources']['memory']['recommended_gi']:.3f} Gi "
                          f"({rec['resources']['memory']['change_percent']:+.1f}%)")
                logger.info(f"   Range: CPU [{rec['resources']['cpu']['min']} - {rec['resources']['cpu']['max']}], "
                          f"Memory [{rec['resources']['memory']['min']} - {rec['resources']['memory']['max']}]")
                logger.info("")
        
        return 0
        
    except Exception as e:
        logger.error(f"VPA application failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
