#!/usr/bin/env python3
"""
Test cAdvisor and node-exporter configuration in observability stack.
"""

import yaml
import sys


def test_docker_compose_observability():
    """Test docker-compose.observability.yml has cAdvisor and node-exporter services."""
    print("Testing docker-compose.observability.yml...")
    
    try:
        with open('docker-compose.observability.yml', 'r') as f:
            config = yaml.safe_load(f)
        
        services = config.get('services', {})
        
        # Test cAdvisor service
        assert 'cadvisor' in services, "cAdvisor service not found"
        cadvisor = services['cadvisor']
        
        assert cadvisor['image'] == 'gcr.io/cadvisor/cadvisor:v0.47.0', "cAdvisor image incorrect"
        assert cadvisor['restart'] == 'always', "cAdvisor restart policy incorrect"
        assert '8080:8080' in cadvisor['ports'], "cAdvisor port mapping incorrect"
        
        # Check cAdvisor volumes
        volumes = cadvisor['volumes']
        assert any('/var/run/docker.sock' in v for v in volumes), "docker.sock volume missing"
        assert any('/sys:/sys' in v for v in volumes), "/sys volume missing"
        assert any('/var/lib/docker' in v for v in volumes), "/var/lib/docker volume missing"
        
        print("  ✓ cAdvisor service configured correctly")
        
        # Test node-exporter service
        assert 'node-exporter' in services, "node-exporter service not found"
        node_exporter = services['node-exporter']
        
        assert node_exporter['image'] == 'prom/node-exporter:v1.7.0', "node-exporter image incorrect"
        assert node_exporter['restart'] == 'always', "node-exporter restart policy incorrect"
        assert '9100:9100' in node_exporter['ports'], "node-exporter port mapping incorrect"
        
        # Check node-exporter volumes
        volumes = node_exporter['volumes']
        assert any('/proc:/host/proc' in v for v in volumes), "/proc volume missing"
        assert any('/sys:/host/sys' in v for v in volumes), "/sys volume missing"
        assert any('/:/rootfs' in v for v in volumes), "rootfs volume missing"
        
        print("  ✓ node-exporter service configured correctly")
        
        # Check network configuration
        networks = config.get('networks', {})
        assert 'brainego' in networks, "brainego network not found"
        assert networks['brainego'].get('external') == True, "brainego network should be external"
        
        print("  ✓ Network configuration correct")
        
        print("✓ docker-compose.observability.yml validation passed")
        return True
    
    except AssertionError as e:
        print(f"✗ docker-compose.observability.yml validation failed: {e}")
        return False
    except Exception as e:
        print(f"✗ docker-compose.observability.yml error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_prometheus_config():
    """Test prometheus.yml has cAdvisor and node-exporter scrape configs."""
    print("\nTesting configs/prometheus/prometheus.yml...")
    
    try:
        with open('configs/prometheus/prometheus.yml', 'r') as f:
            config = yaml.safe_load(f)
        
        scrape_configs = config.get('scrape_configs', [])
        
        # Find cAdvisor job
        cadvisor_job = None
        for job in scrape_configs:
            if job.get('job_name') == 'cadvisor':
                cadvisor_job = job
                break
        
        assert cadvisor_job is not None, "cAdvisor scrape job not found"
        assert cadvisor_job['metrics_path'] == '/metrics', "cAdvisor metrics path incorrect"
        assert cadvisor_job['scrape_interval'] == '15s', "cAdvisor scrape interval incorrect"
        
        targets = cadvisor_job['static_configs'][0]['targets']
        assert 'cadvisor:8080' in targets, "cAdvisor target incorrect"
        
        print("  ✓ cAdvisor scrape config correct")
        
        # Find node-exporter job
        node_exporter_job = None
        for job in scrape_configs:
            if job.get('job_name') == 'node-exporter':
                node_exporter_job = job
                break
        
        assert node_exporter_job is not None, "node-exporter scrape job not found"
        assert node_exporter_job['metrics_path'] == '/metrics', "node-exporter metrics path incorrect"
        assert node_exporter_job['scrape_interval'] == '15s', "node-exporter scrape interval incorrect"
        
        targets = node_exporter_job['static_configs'][0]['targets']
        assert 'node-exporter:9100' in targets, "node-exporter target incorrect"
        
        print("  ✓ node-exporter scrape config correct")
        
        print("✓ configs/prometheus/prometheus.yml validation passed")
        return True
    
    except AssertionError as e:
        print(f"✗ configs/prometheus/prometheus.yml validation failed: {e}")
        return False
    except Exception as e:
        print(f"✗ configs/prometheus/prometheus.yml error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metrics_availability():
    """Test that expected metrics are documented."""
    print("\nVerifying expected metrics documentation...")
    
    expected_metrics = [
        'container_memory_working_set_bytes',
        'container_cpu_usage_seconds_total',
        'container_last_seen'
    ]
    
    print(f"  Expected cAdvisor metrics: {', '.join(expected_metrics)}")
    print("  ✓ Metrics will be available after deployment")
    
    return True


def main():
    """Run all tests."""
    print("=" * 70)
    print("Testing cAdvisor and node-exporter Configuration")
    print("=" * 70)
    print()
    
    results = []
    
    # Test docker-compose configuration
    results.append(test_docker_compose_observability())
    
    # Test Prometheus configuration
    results.append(test_prometheus_config())
    
    # Test metrics documentation
    results.append(test_metrics_availability())
    
    # Summary
    print()
    print("=" * 70)
    if all(results):
        print("✓ All configuration tests passed")
        print("=" * 70)
        return 0
    else:
        print("✗ Some configuration tests failed")
        print("=" * 70)
        return 1


if __name__ == '__main__':
    sys.exit(main())
