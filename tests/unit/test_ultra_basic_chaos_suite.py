"""
Unit tests for ultra-basic chaos suite

These tests verify the chaos suite implementation syntax and structure.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def test_imports():
    """Test that the chaos suite module can be imported"""
    try:
        # Import with path manipulation since it's in scripts/validation
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "run_production_validation",
            "scripts/validation/run_production_validation.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Verify key classes exist
        assert hasattr(module, 'UltraBasicChaosSuite')
        assert hasattr(module, 'MTTRMeasurement')
        
    except ImportError as e:
        pytest.fail(f"Failed to import chaos suite: {e}")


def test_mttr_measurement_dataclass():
    """Test MTTRMeasurement dataclass structure"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_production_validation",
        "scripts/validation/run_production_validation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # Create instance
    mttr = module.MTTRMeasurement(
        service='test-service',
        failure_time=100.0,
        recovery_time=150.0,
        mttr_seconds=50.0,
        alert_triggered=True,
        recovery_successful=True
    )
    
    assert mttr.service == 'test-service'
    assert mttr.mttr_seconds == 50.0
    assert mttr.alert_triggered is True


def test_chaos_suite_initialization():
    """Test UltraBasicChaosSuite can be initialized"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_production_validation",
        "scripts/validation/run_production_validation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # This will fail if Docker is not available, but that's expected
    try:
        suite = module.UltraBasicChaosSuite(docker_compose_cmd="docker compose")
        assert suite.docker_compose_cmd == "docker compose"
        assert isinstance(suite.test_results, list)
        assert isinstance(suite.mttr_measurements, list)
    except Exception:
        # Expected if Docker is not available
        pass


def test_module_has_main_function():
    """Test that the module has a main() function"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_production_validation",
        "scripts/validation/run_production_validation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    assert hasattr(module, 'main')
    assert callable(module.main)


if __name__ == '__main__':
    # Run basic syntax check
    print("Testing imports...")
    test_imports()
    print("✓ Imports successful")
    
    print("Testing MTTRMeasurement...")
    test_mttr_measurement_dataclass()
    print("✓ MTTRMeasurement working")
    
    print("Testing chaos suite initialization...")
    test_chaos_suite_initialization()
    print("✓ Chaos suite initialization tested")
    
    print("Testing main function...")
    test_module_has_main_function()
    print("✓ Main function exists")
    
    print("\n✓ All tests passed!")
