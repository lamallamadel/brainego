#!/usr/bin/env python3
"""Test that chaos engineering modules can be imported."""

import sys

def test_imports():
    """Test all chaos engineering related imports."""
    errors = []
    
    # Test chaos_engineering module
    try:
        import chaos_engineering
        print("✓ chaos_engineering module imports successfully")
    except Exception as e:
        errors.append(f"chaos_engineering: {e}")
        print(f"✗ chaos_engineering import failed: {e}")
    
    # Test run_production_validation module
    try:
        import run_production_validation
        print("✓ run_production_validation module imports successfully")
    except Exception as e:
        errors.append(f"run_production_validation: {e}")
        print(f"✗ run_production_validation import failed: {e}")
    
    # Test circuit_breaker module
    try:
        import circuit_breaker
        print("✓ circuit_breaker module imports successfully")
        
        # Check that metrics support is available
        if hasattr(circuit_breaker, 'METRICS_AVAILABLE'):
            print(f"  - Metrics available: {circuit_breaker.METRICS_AVAILABLE}")
    except Exception as e:
        errors.append(f"circuit_breaker: {e}")
        print(f"✗ circuit_breaker import failed: {e}")
    
    # Test metrics_exporter module
    try:
        import metrics_exporter
        print("✓ metrics_exporter module imports successfully")
        
        try:
            # Check MetricsExporter class
            exporter = metrics_exporter.MetricsExporter('test-service')
            
            # Check new methods exist
            assert hasattr(exporter, 'record_circuit_breaker_request')
            assert hasattr(exporter, 'record_chaos_test')
            assert hasattr(exporter, 'set_network_partition')
            print("  - New chaos engineering methods available")
        except ImportError as ie:
            # prometheus_client not available, but that's OK
            print(f"  - Metrics exporter requires prometheus_client (optional dependency)")
    except Exception as e:
        errors.append(f"metrics_exporter: {e}")
        print(f"✗ metrics_exporter import/test failed: {e}")
    
    if errors:
        print(f"\n✗ {len(errors)} import errors detected")
        for error in errors:
            print(f"  - {error}")
        return False
    else:
        print("\n✓ All chaos engineering modules import successfully")
        return True

if __name__ == '__main__':
    success = test_imports()
    sys.exit(0 if success else 1)
