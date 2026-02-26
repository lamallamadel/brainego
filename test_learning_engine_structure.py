#!/usr/bin/env python3
"""Test learning engine structure and configuration"""

import sys
import os
import json

def test_file_exists(file_path):
    """Test if file exists"""
    if os.path.exists(file_path):
        print(f"✓ {file_path} exists")
        return True
    else:
        print(f"✗ {file_path} missing")
        return False

def test_directory_structure():
    """Test directory structure"""
    results = []
    
    # Test main files
    main_files = [
        'learning_engine_service.py',
        'learning_engine_cli.py',
        'test_learning_engine.py',
    ]
    
    for file_path in main_files:
        results.append(test_file_exists(file_path))
    
    # Test package structure
    package_files = [
        'learning_engine/__init__.py',
        'learning_engine/fisher.py',
        'learning_engine/trainer.py',
        'learning_engine/storage.py',
        'learning_engine/scheduler.py',
        'learning_engine/data_loader.py',
    ]
    
    for file_path in package_files:
        results.append(test_file_exists(file_path))
    
    # Test config files
    config_files = [
        'configs/learning-engine.yaml',
        '.env.learning.example',
    ]
    
    for file_path in config_files:
        results.append(test_file_exists(file_path))
    
    # Test documentation
    doc_files = [
        'LEARNING_ENGINE_README.md',
        'LEARNING_ENGINE_QUICKSTART.md',
        'LEARNING_ENGINE_IMPLEMENTATION.md',
    ]
    
    for file_path in doc_files:
        results.append(test_file_exists(file_path))
    
    return all(results)

def test_configuration_validity():
    """Test configuration file structure"""
    config_file = 'configs/learning-engine.yaml'
    
    if not os.path.exists(config_file):
        print(f"✗ Config file missing: {config_file}")
        return False
    
    # Basic check - file is readable
    try:
        with open(config_file, 'r') as f:
            content = f.read()
            if len(content) > 0:
                print(f"✓ {config_file} is readable and non-empty")
                return True
            else:
                print(f"✗ {config_file} is empty")
                return False
    except Exception as e:
        print(f"✗ Error reading {config_file}: {e}")
        return False

def test_docker_compose_update():
    """Test docker-compose.yaml has learning-engine service"""
    try:
        with open('docker-compose.yaml', 'r') as f:
            content = f.read()
            if 'learning-engine:' in content:
                print("✓ docker-compose.yaml includes learning-engine service")
                return True
            else:
                print("✗ docker-compose.yaml missing learning-engine service")
                return False
    except Exception as e:
        print(f"✗ Error checking docker-compose.yaml: {e}")
        return False

def main():
    """Main test runner"""
    results = []
    
    print("Testing Learning Engine Structure\n")
    print("=" * 60)
    
    print("\n1. Testing directory structure...")
    results.append(test_directory_structure())
    
    print("\n2. Testing configuration...")
    results.append(test_configuration_validity())
    
    print("\n3. Testing Docker integration...")
    results.append(test_docker_compose_update())
    
    print("\n" + "=" * 60)
    if all(results):
        print("✓ All structure tests passed")
        sys.exit(0)
    else:
        print("✗ Some structure tests failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
