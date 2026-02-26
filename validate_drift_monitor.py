#!/usr/bin/env python3
"""
Validation script for Drift Monitor implementation
Checks code structure and required components without running the service
"""

import ast
import os
import sys

def validate_python_file(filepath):
    """Check if Python file has valid syntax"""
    print(f"\nValidating {filepath}...")
    try:
        with open(filepath, 'r') as f:
            code = f.read()
            ast.parse(code)
        print(f"✓ {filepath} has valid Python syntax")
        return True
    except SyntaxError as e:
        print(f"✗ {filepath} has syntax error: {e}")
        return False
    except FileNotFoundError:
        print(f"✗ {filepath} not found")
        return False

def check_required_methods(filepath, required_methods):
    """Check if required methods exist in file"""
    print(f"\nChecking required methods in {filepath}...")
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        
        found_methods = []
        missing_methods = []
        
        for method in required_methods:
            if f"def {method}" in code or f"async def {method}" in code:
                found_methods.append(method)
                print(f"  ✓ {method}")
            else:
                missing_methods.append(method)
                print(f"  ✗ {method} NOT FOUND")
        
        return len(missing_methods) == 0
    except FileNotFoundError:
        print(f"✗ {filepath} not found")
        return False

def check_config_values(filepath, required_keys):
    """Check if YAML config has required keys"""
    print(f"\nChecking required config keys in {filepath}...")
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        found_keys = []
        missing_keys = []
        
        for key in required_keys:
            if f"{key}:" in content:
                found_keys.append(key)
                print(f"  ✓ {key}")
            else:
                missing_keys.append(key)
                print(f"  ✗ {key} NOT FOUND")
        
        return len(missing_keys) == 0
    except FileNotFoundError:
        print(f"✗ {filepath} not found")
        return False

def check_database_tables(filepath, required_tables):
    """Check if SQL file creates required tables"""
    print(f"\nChecking required tables in {filepath}...")
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        found_tables = []
        missing_tables = []
        
        for table in required_tables:
            if f"CREATE TABLE" in content and table in content:
                found_tables.append(table)
                print(f"  ✓ {table}")
            else:
                missing_tables.append(table)
                print(f"  ✗ {table} NOT FOUND")
        
        return len(missing_tables) == 0
    except FileNotFoundError:
        print(f"✗ {filepath} not found")
        return False

def check_docker_service(filepath, service_name):
    """Check if docker-compose has the service"""
    print(f"\nChecking for {service_name} service in {filepath}...")
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        if f"{service_name}:" in content:
            print(f"  ✓ {service_name} service found")
            return True
        else:
            print(f"  ✗ {service_name} service NOT FOUND")
            return False
    except FileNotFoundError:
        print(f"✗ {filepath} not found")
        return False

def main():
    print("=" * 60)
    print("Drift Monitor Implementation Validation")
    print("=" * 60)
    
    all_valid = True
    
    # 1. Check Python files syntax
    print("\n1. PYTHON SYNTAX VALIDATION")
    print("-" * 60)
    all_valid &= validate_python_file("drift_monitor.py")
    all_valid &= validate_python_file("test_drift_monitor.py")
    
    # 2. Check required methods in drift_monitor.py
    print("\n2. REQUIRED METHODS VALIDATION")
    print("-" * 60)
    required_methods = [
        "calculate_kl_divergence",
        "calculate_psi",
        "send_slack_alert",
        "trigger_finetuning",
        "run_drift_check",
        "get_feedback_data",
        "compute_embeddings"
    ]
    all_valid &= check_required_methods("drift_monitor.py", required_methods)
    
    # 3. Check configuration file
    print("\n3. CONFIGURATION VALIDATION")
    print("-" * 60)
    required_config = [
        "kl_threshold",
        "psi_threshold",
        "accuracy_min",
        "sliding_window_days"
    ]
    all_valid &= check_config_values("configs/drift-monitor.yaml", required_config)
    
    # 4. Check database schema
    print("\n4. DATABASE SCHEMA VALIDATION")
    print("-" * 60)
    required_tables = [
        "drift_metrics",
        "finetuning_triggers"
    ]
    all_valid &= check_database_tables("init-scripts/postgres/init.sql", required_tables)
    
    # 5. Check docker-compose
    print("\n5. DOCKER COMPOSE VALIDATION")
    print("-" * 60)
    all_valid &= check_docker_service("docker-compose.yaml", "drift-monitor")
    
    # 6. Check dependencies
    print("\n6. DEPENDENCIES VALIDATION")
    print("-" * 60)
    try:
        with open("requirements.txt", 'r') as f:
            content = f.read()
            if "scipy" in content:
                print("  ✓ scipy dependency added")
            else:
                print("  ✗ scipy dependency NOT FOUND")
                all_valid = False
    except FileNotFoundError:
        print("  ✗ requirements.txt not found")
        all_valid = False
    
    # 7. Check documentation
    print("\n7. DOCUMENTATION VALIDATION")
    print("-" * 60)
    docs = [
        "DRIFT_MONITOR_README.md",
        "DRIFT_MONITOR_QUICKSTART.md",
        "DRIFT_MONITOR_IMPLEMENTATION.md"
    ]
    for doc in docs:
        if os.path.exists(doc):
            print(f"  ✓ {doc} exists")
        else:
            print(f"  ✗ {doc} NOT FOUND")
            all_valid = False
    
    # Summary
    print("\n" + "=" * 60)
    if all_valid:
        print("✓ ALL VALIDATIONS PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ SOME VALIDATIONS FAILED")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
