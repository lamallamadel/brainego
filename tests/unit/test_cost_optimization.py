#!/usr/bin/env python3
"""
Unit tests for cost optimization components.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime


class TestResourceAnalyzer(unittest.TestCase):
    """Tests for resource usage analyzer."""

    def test_prometheus_client_init(self):
        """Test PrometheusClient initialization."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'scripts', 'observability'))
        
        from analyze_resource_usage import PrometheusClient
        
        client = PrometheusClient("http://test-prometheus:9090")
        self.assertEqual(client.prometheus_url, "http://test-prometheus:9090")
        self.assertEqual(client.timeout, 30)

    def test_resource_analyzer_thresholds(self):
        """Test ResourceAnalyzer threshold configuration."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'scripts', 'observability'))
        
        from analyze_resource_usage import ResourceAnalyzer, PrometheusClient
        
        prom_client = PrometheusClient("http://test:9090")
        analyzer = ResourceAnalyzer(prom_client)
        
        self.assertEqual(analyzer.cpu_underutilization_threshold, 0.40)
        self.assertEqual(analyzer.memory_underutilization_threshold, 0.40)
        self.assertEqual(analyzer.cpu_overutilization_threshold, 0.85)
        self.assertEqual(analyzer.memory_overutilization_threshold, 0.85)
        self.assertEqual(analyzer.cpu_buffer, 1.2)
        self.assertEqual(analyzer.memory_buffer, 1.2)

    def test_cost_savings_calculation(self):
        """Test cost savings estimation."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'scripts', 'observability'))
        
        from analyze_resource_usage import ResourceAnalyzer, PrometheusClient
        
        prom_client = PrometheusClient("http://test:9090")
        analyzer = ResourceAnalyzer(prom_client)
        
        recommendations = [
            {
                "potential_savings": {
                    "cpu_cores": 2.0,
                    "memory_gi": 4.0
                }
            },
            {
                "potential_savings": {
                    "cpu_cores": 1.5,
                    "memory_gi": 3.0
                }
            }
        ]
        
        savings = analyzer.estimate_cost_savings(recommendations)
        
        # Expected: (3.5 cores * $30) + (7.0 GB * $4) = $105 + $28 = $133/month
        self.assertEqual(savings["total_cpu_cores_saved"], 3.5)
        self.assertEqual(savings["total_memory_gi_saved"], 7.0)
        self.assertEqual(savings["estimated_monthly_savings_usd"], 133.0)
        self.assertEqual(savings["estimated_annual_savings_usd"], 1596.0)


class TestQdrantArchival(unittest.TestCase):
    """Tests for Qdrant archival service."""

    def test_archival_service_init(self):
        """Test QdrantArchivalService initialization."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'scripts', 'observability'))
        
        # Mock dependencies
        with patch('qdrant_archival_service.QdrantClient'):
            with patch('qdrant_archival_service.Minio'):
                from qdrant_archival_service import QdrantArchivalService
                
                service = QdrantArchivalService(
                    qdrant_host="test-qdrant",
                    qdrant_port=6333,
                    minio_endpoint="test-minio:9000",
                    minio_access_key="test-key",
                    minio_secret_key="test-secret",
                    archival_age_days=90,
                    batch_size=1000,
                    dry_run=True
                )
                
                self.assertEqual(service.archival_age_days, 90)
                self.assertEqual(service.batch_size, 1000)
                self.assertTrue(service.dry_run)


class TestRecommendationApplier(unittest.TestCase):
    """Tests for recommendation applier."""

    def test_load_recommendations(self):
        """Test loading recommendations from JSON file."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'scripts', 'observability'))
        
        from apply_recommendations import RecommendationApplier
        
        # Create temporary recommendations file
        recommendations = {
            "generated_at": datetime.utcnow().isoformat(),
            "lookback_days": 7,
            "summary": {
                "total_workloads_analyzed": 10,
                "recommendations_generated": 5
            },
            "recommendations": [
                {
                    "namespace": "ai-platform",
                    "workload": "api-server",
                    "container": "api-server",
                    "action": "reduce_cpu",
                    "current": {"cpu_request_cores": 2.0},
                    "recommendation": {"cpu_request_cores": 1.0}
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(recommendations, f)
            temp_file = f.name
        
        try:
            applier = RecommendationApplier(temp_file, dry_run=True)
            self.assertEqual(len(applier.recommendations), 1)
            self.assertEqual(applier.recommendations[0]["workload"], "api-server")
        finally:
            os.unlink(temp_file)

    def test_helm_values_patch_generation(self):
        """Test Helm values patch generation."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'scripts', 'observability'))
        
        from apply_recommendations import RecommendationApplier
        
        # Create temporary recommendations file
        recommendations = {
            "generated_at": datetime.utcnow().isoformat(),
            "lookback_days": 7,
            "summary": {},
            "recommendations": [
                {
                    "namespace": "ai-platform",
                    "workload": "api-server",
                    "container": "api-server",
                    "action": "reduce_both",
                    "current": {
                        "cpu_request_cores": 2.0,
                        "memory_request_gi": 4.0
                    },
                    "recommendation": {
                        "cpu_request_cores": 1.0,
                        "memory_request_gi": 2.0
                    }
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(recommendations, f)
            temp_file = f.name
        
        try:
            applier = RecommendationApplier(temp_file, dry_run=True)
            patch = applier.generate_helm_values_patch()
            
            self.assertIn("apiServer", patch)
            self.assertIn("resources", patch["apiServer"])
            self.assertIn("requests", patch["apiServer"]["resources"])
            self.assertEqual(patch["apiServer"]["resources"]["requests"]["cpu"], "1")
            self.assertEqual(patch["apiServer"]["resources"]["requests"]["memory"], "2.0Gi")
        finally:
            os.unlink(temp_file)


class TestHelmVPAManifest(unittest.TestCase):
    """Tests for VPA Helm manifests."""

    def test_vpa_manifest_structure(self):
        """Test VPA manifest has correct structure."""
        vpa_file = os.path.join(
            os.path.dirname(__file__), '../..', 
            'helm', 'ai-platform', 'templates', 'vpa.yaml'
        )
        
        self.assertTrue(os.path.exists(vpa_file), "VPA manifest file should exist")
        
        with open(vpa_file, 'r') as f:
            content = f.read()
        
        # Check for key VPA components
        self.assertIn("apiVersion: autoscaling.k8s.io/v1", content)
        self.assertIn("kind: VerticalPodAutoscaler", content)
        self.assertIn("gateway-vpa", content)
        self.assertIn("mcpjungle-vpa", content)
        self.assertIn("mem0-vpa", content)
        self.assertIn("grafana-vpa", content)
        self.assertIn("jaeger-vpa", content)
        self.assertIn("updatePolicy", content)
        self.assertIn("resourcePolicy", content)
        self.assertIn("minAllowed", content)
        self.assertIn("maxAllowed", content)


class TestGrafanaDashboard(unittest.TestCase):
    """Tests for Grafana cost dashboard."""

    def test_dashboard_structure(self):
        """Test dashboard JSON has correct structure."""
        dashboard_file = os.path.join(
            os.path.dirname(__file__), '../..', 
            'configs', 'grafana', 'dashboards', 'cost-optimization.json'
        )
        
        self.assertTrue(os.path.exists(dashboard_file), "Dashboard file should exist")
        
        with open(dashboard_file, 'r') as f:
            dashboard = json.load(f)
        
        # Check basic dashboard structure
        self.assertIn("panels", dashboard)
        self.assertIn("title", dashboard)
        self.assertEqual(dashboard["title"], "Cost Optimization & FinOps")
        self.assertIn("cost", dashboard.get("tags", []))
        
        # Check for required panels
        panel_titles = [panel.get("title", "") for panel in dashboard["panels"]]
        self.assertIn("Estimated Monthly Cost (All Workspaces)", panel_titles)
        self.assertIn("Cost Trend by Workspace (Hourly)", panel_titles)
        self.assertIn("Token Usage & Cost by Workspace (Last 30 Days)", panel_titles)


class TestArchivalCronJob(unittest.TestCase):
    """Tests for Qdrant archival CronJob manifest."""

    def test_cronjob_manifest_structure(self):
        """Test CronJob manifest has correct structure."""
        cronjob_file = os.path.join(
            os.path.dirname(__file__), '../..', 
            'helm', 'ai-platform', 'templates', 'qdrant-archival-cronjob.yaml'
        )
        
        self.assertTrue(os.path.exists(cronjob_file), "CronJob manifest file should exist")
        
        with open(cronjob_file, 'r') as f:
            content = f.read()
        
        # Check for key CronJob components
        self.assertIn("apiVersion: batch/v1", content)
        self.assertIn("kind: CronJob", content)
        self.assertIn("name: qdrant-archival", content)
        self.assertIn("schedule:", content)
        self.assertIn("concurrencyPolicy: Forbid", content)
        self.assertIn("qdrant_archival_service.py", content)


if __name__ == '__main__':
    unittest.main()
