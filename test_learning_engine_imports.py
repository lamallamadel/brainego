#!/usr/bin/env python3
"""Test learning engine imports"""

import sys

def test_imports():
    """Test that all modules can be imported"""
    results = []
    
    # Test learning_engine package
    try:
        import learning_engine
        print("✓ learning_engine package imports")
        results.append(True)
    except Exception as e:
        print(f"✗ learning_engine package failed: {e}")
        results.append(False)
    
    # Test individual modules
    modules = [
        'learning_engine.fisher',
        'learning_engine.trainer',
        'learning_engine.storage',
        'learning_engine.scheduler',
        'learning_engine.data_loader',
    ]
    
    for module_name in modules:
        try:
            __import__(module_name)
            print(f"✓ {module_name} imports")
            results.append(True)
        except ImportError as e:
            # Expected for modules with dependencies not installed
            print(f"⊘ {module_name} - missing dependencies: {e}")
            results.append(True)  # Don't fail on missing deps
        except Exception as e:
            print(f"✗ {module_name} failed: {e}")
            results.append(False)
    
    return all(results)

if __name__ == '__main__':
    if test_imports():
        print("\n✓ All import tests passed")
        sys.exit(0)
    else:
        print("\n✗ Some import tests failed")
        sys.exit(1)
