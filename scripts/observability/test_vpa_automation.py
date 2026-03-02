#!/usr/bin/env python3
"""
Test script for VPA automation with sample data.
Demonstrates the VPA manifest generation without requiring live Prometheus data.
"""

import json
import tempfile
import os
from pathlib import Path

# Sample recommendations data (simulating output from analyze_resource_usage.py)
SAMPLE_RECOMMENDATIONS = {
    "generated_at": "2025-01-01T00:00:00.000000",
    "lookback_days": 7,
    "summary": {
        "total_workloads_analyzed": 15,
        "recommendations_generated": 12,
        "cost_savings": {
            "total_cpu_cores_saved": 3.5,
            "total_memory_gi_saved": 8.2,
            "estimated_monthly_savings_usd": 137.80,
            "estimated_annual_savings_usd": 1653.60
        }
    },
    "recommendations": [
        {
            "namespace": "ai-platform",
            "workload": "api-server",
            "container": "api-server",
            "current": {
                "cpu_request_cores": 1.0,
                "memory_request_gi": 2.0
            },
            "usage": {
                "cpu_p95_cores": 0.45,
                "memory_p95_gi": 1.2
            },
            "utilization": {
                "cpu_percent": 45.0,
                "memory_percent": 60.0
            },
            "recommendation": {
                "cpu_request_cores": 0.54,
                "memory_request_gi": 1.44
            },
            "action": "reduce_both",
            "potential_savings": {
                "cpu_cores": 0.46,
                "memory_gi": 0.56
            }
        },
        {
            "namespace": "ai-platform",
            "workload": "gateway",
            "container": "gateway",
            "current": {
                "cpu_request_cores": 0.5,
                "memory_request_gi": 1.0
            },
            "usage": {
                "cpu_p95_cores": 0.3,
                "memory_p95_gi": 0.6
            },
            "utilization": {
                "cpu_percent": 60.0,
                "memory_percent": 60.0
            },
            "recommendation": {
                "cpu_request_cores": 0.36,
                "memory_request_gi": 0.72
            },
            "action": "reduce_both",
            "potential_savings": {
                "cpu_cores": 0.14,
                "memory_gi": 0.28
            }
        },
        {
            "namespace": "ai-platform",
            "workload": "mcpjungle",
            "container": "mcpjungle",
            "current": {
                "cpu_request_cores": 2.0,
                "memory_request_gi": 4.0
            },
            "usage": {
                "cpu_p95_cores": 0.8,
                "memory_p95_gi": 2.0
            },
            "utilization": {
                "cpu_percent": 40.0,
                "memory_percent": 50.0
            },
            "recommendation": {
                "cpu_request_cores": 0.96,
                "memory_request_gi": 2.4
            },
            "action": "reduce_both",
            "potential_savings": {
                "cpu_cores": 1.04,
                "memory_gi": 1.6
            }
        },
        {
            "namespace": "ai-platform",
            "workload": "redis",
            "container": "redis",
            "current": {
                "cpu_request_cores": 1.0,
                "memory_request_gi": 2.0
            },
            "usage": {
                "cpu_p95_cores": 0.35,
                "memory_p95_gi": 1.0
            },
            "utilization": {
                "cpu_percent": 35.0,
                "memory_percent": 50.0
            },
            "recommendation": {
                "cpu_request_cores": 0.42,
                "memory_request_gi": 1.2
            },
            "action": "reduce_both",
            "potential_savings": {
                "cpu_cores": 0.58,
                "memory_gi": 0.8
            }
        },
        {
            "namespace": "ai-platform",
            "workload": "qdrant",
            "container": "qdrant",
            "current": {
                "cpu_request_cores": 2.0,
                "memory_request_gi": 4.0
            },
            "usage": {
                "cpu_p95_cores": 1.0,
                "memory_p95_gi": 2.5
            },
            "utilization": {
                "cpu_percent": 50.0,
                "memory_percent": 62.5
            },
            "recommendation": {
                "cpu_request_cores": 1.2,
                "memory_request_gi": 3.0
            },
            "action": "reduce_both",
            "potential_savings": {
                "cpu_cores": 0.8,
                "memory_gi": 1.0
            }
        },
        {
            "namespace": "ai-platform",
            "workload": "postgres",
            "container": "postgres",
            "current": {
                "cpu_request_cores": 2.0,
                "memory_request_gi": 8.0
            },
            "usage": {
                "cpu_p95_cores": 0.6,
                "memory_p95_gi": 4.0
            },
            "utilization": {
                "cpu_percent": 30.0,
                "memory_percent": 50.0
            },
            "recommendation": {
                "cpu_request_cores": 0.72,
                "memory_request_gi": 4.8
            },
            "action": "reduce_both",
            "potential_savings": {
                "cpu_cores": 1.28,
                "memory_gi": 3.2
            }
        },
        {
            "namespace": "ai-platform",
            "workload": "prometheus",
            "container": "prometheus",
            "current": {
                "cpu_request_cores": 1.0,
                "memory_request_gi": 4.0
            },
            "usage": {
                "cpu_p95_cores": 0.85,
                "memory_p95_gi": 3.2
            },
            "utilization": {
                "cpu_percent": 85.0,
                "memory_percent": 80.0
            },
            "recommendation": {
                "cpu_request_cores": 1.02,
                "memory_request_gi": 3.84
            },
            "action": "none",
            "potential_savings": {}
        },
        {
            "namespace": "ai-platform",
            "workload": "grafana",
            "container": "grafana",
            "current": {
                "cpu_request_cores": 0.5,
                "memory_request_gi": 1.0
            },
            "usage": {
                "cpu_p95_cores": 0.15,
                "memory_p95_gi": 0.4
            },
            "utilization": {
                "cpu_percent": 30.0,
                "memory_percent": 40.0
            },
            "recommendation": {
                "cpu_request_cores": 0.18,
                "memory_request_gi": 0.48
            },
            "action": "reduce_both",
            "potential_savings": {
                "cpu_cores": 0.32,
                "memory_gi": 0.52
            }
        }
    ]
}


def test_vpa_automation():
    """Test VPA automation with sample data."""
    import sys
    from pathlib import Path
    
    # Add parent directory to path to import the module
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    
    from apply_vpa_recommendations import VPAManifestGenerator
    
    print("=" * 80)
    print("VPA Automation Test with Sample Data")
    print("=" * 80)
    print()
    
    # Create temporary directory for outputs
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Write sample recommendations
        recommendations_file = tmpdir_path / "recommendations.json"
        with open(recommendations_file, 'w') as f:
            json.dump(SAMPLE_RECOMMENDATIONS, f, indent=2)
        
        print(f"✓ Created sample recommendations: {recommendations_file}")
        print(f"  - Workloads: {len(SAMPLE_RECOMMENDATIONS['recommendations'])}")
        print(f"  - Potential savings: ${SAMPLE_RECOMMENDATIONS['summary']['cost_savings']['estimated_monthly_savings_usd']}/month")
        print()
        
        # Initialize VPA generator in dry-run mode
        generator = VPAManifestGenerator(namespace="ai-platform", dry_run=True)
        
        # Generate VPA manifests
        print("Generating VPA manifests...")
        vpas = generator.generate_all_vpas(SAMPLE_RECOMMENDATIONS["recommendations"])
        print(f"✓ Generated {len(vpas)} VPA manifests")
        print()
        
        # Write outputs
        helm_template = tmpdir_path / "vpa.yaml"
        raw_dir = tmpdir_path / "vpa_raw"
        summary_file = tmpdir_path / "summary.json"
        
        generator.write_helm_template(str(helm_template))
        generator.write_raw_manifests(str(raw_dir))
        
        summary = generator.generate_summary_report()
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"✓ Wrote Helm template: {helm_template}")
        print(f"✓ Wrote raw manifests: {raw_dir}/")
        print(f"✓ Wrote summary: {summary_file}")
        print()
        
        # Print summary
        print("=" * 80)
        print("Summary Report")
        print("=" * 80)
        print()
        print(f"Total VPAs generated: {summary['summary']['total_vpas_generated']}")
        print(f"Update modes:")
        print(f"  - Auto (non-critical): {summary['update_modes']['auto']}")
        print(f"  - Initial (StatefulSets): {summary['update_modes']['initial']}")
        print()
        print("Cost Savings Potential:")
        print(f"  CPU cores saved: {summary['cost_savings']['total_cpu_cores_saved']}")
        print(f"  Memory saved: {summary['cost_savings']['total_memory_gi_saved']} Gi")
        print(f"  Monthly savings: ${summary['cost_savings']['estimated_monthly_savings_usd']}")
        print(f"  Annual savings: ${summary['cost_savings']['estimated_annual_savings_usd']}")
        print()
        
        # Show sample VPA configurations
        print("=" * 80)
        print("Sample VPA Configurations")
        print("=" * 80)
        print()
        
        for i, rec in enumerate(summary['applied_recommendations'][:5], 1):
            print(f"{i}. {rec['workload']} ({rec['container']})")
            print(f"   Mode: {rec['update_mode']} ({rec['workload_kind']})")
            print(f"   CPU: {rec['resources']['cpu']['current_cores']:.3f} → "
                  f"{rec['resources']['cpu']['recommended_cores']:.3f} cores "
                  f"({rec['resources']['cpu']['change_percent']:+.1f}%)")
            print(f"   Memory: {rec['resources']['memory']['current_gi']:.3f} → "
                  f"{rec['resources']['memory']['recommended_gi']:.3f} Gi "
                  f"({rec['resources']['memory']['change_percent']:+.1f}%)")
            print(f"   Bounds: CPU [{rec['resources']['cpu']['min']} - {rec['resources']['cpu']['max']}], "
                  f"Memory [{rec['resources']['memory']['min']} - {rec['resources']['memory']['max']}]")
            print()
        
        # Show validation results
        if summary['validation_errors']:
            print("=" * 80)
            print("Validation Errors (Changes Rejected)")
            print("=" * 80)
            print()
            for error in summary['validation_errors']:
                print(f"- {error['resource_type']}: {error['reason']}")
                print(f"  Current: {error['current']:.3f}, Recommended: {error['recommended']:.3f}")
                print(f"  Change: {error['change_percent']}%")
                print()
        
        print("=" * 80)
        print("Test Complete")
        print("=" * 80)
        print()
        print("To apply these recommendations in production:")
        print("  1. Run: python scripts/observability/analyze_resource_usage.py")
        print("  2. Run: DRY_RUN=false python scripts/observability/apply_vpa_recommendations.py")
        print("  3. Deploy: helm upgrade ai-platform helm/ai-platform --set vpa.enabled=true")
        print()


if __name__ == "__main__":
    test_vpa_automation()
