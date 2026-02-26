#!/usr/bin/env python3
"""
Validation script for data collection pipeline implementation.
Checks that all files exist and have valid Python syntax.
"""

import os
import sys
import py_compile
import ast

def validate_file_exists(filepath):
    """Check if file exists."""
    if os.path.exists(filepath):
        print(f"✓ {filepath}")
        return True
    else:
        print(f"✗ {filepath} - NOT FOUND")
        return False

def validate_python_syntax(filepath):
    """Check if Python file has valid syntax."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        ast.parse(code)
        py_compile.compile(filepath, doraise=True)
        return True
    except SyntaxError as e:
        print(f"✗ {filepath} - SYNTAX ERROR: {e}")
        return False
    except Exception as e:
        print(f"✗ {filepath} - ERROR: {e}")
        return False

def main():
    """Run validation."""
    print("=" * 60)
    print("Data Collection Pipeline - Implementation Validation")
    print("=" * 60)
    
    all_valid = True
    
    # Core pipeline files
    print("\n1. Core Pipeline Files:")
    core_files = [
        "data_collectors/__init__.py",
        "data_collectors/github_collector.py",
        "data_collectors/notion_collector.py",
        "data_collectors/slack_collector.py",
        "data_collectors/format_normalizer.py",
        "data_collectors/deduplicator.py",
        "data_collectors/ingestion_queue.py",
        "data_collectors/ingestion_worker.py",
        "data_collectors/scheduler.py",
        "data_collectors/webhook_endpoints.py"
    ]
    
    for filepath in core_files:
        if validate_file_exists(filepath):
            if not validate_python_syntax(filepath):
                all_valid = False
        else:
            all_valid = False
    
    # Main services
    print("\n2. Main Services:")
    service_files = [
        "data_collection_service.py",
        "worker_service.py",
        "test_data_collection.py"
    ]
    
    for filepath in service_files:
        if validate_file_exists(filepath):
            if not validate_python_syntax(filepath):
                all_valid = False
        else:
            all_valid = False
    
    # Configuration files
    print("\n3. Configuration Files:")
    config_files = [
        "configs/collection-schedule.yaml",
        ".env.datacollection.example"
    ]
    
    for filepath in config_files:
        if not validate_file_exists(filepath):
            all_valid = False
    
    # Documentation
    print("\n4. Documentation Files:")
    doc_files = [
        "DATA_COLLECTION_README.md",
        "DATA_COLLECTION_QUICKSTART.md",
        "DATA_COLLECTION_IMPLEMENTATION.md",
        "DATA_COLLECTION_FILES_CREATED.md",
        "DATA_COLLECTION_CHANGELOG.md",
        "DATA_COLLECTION_SUMMARY.md"
    ]
    
    for filepath in doc_files:
        if not validate_file_exists(filepath):
            all_valid = False
    
    # Examples
    print("\n5. Example Files:")
    example_files = [
        "examples/data_collection_examples.py"
    ]
    
    for filepath in example_files:
        if validate_file_exists(filepath):
            if not validate_python_syntax(filepath):
                all_valid = False
        else:
            all_valid = False
    
    # Check updated files
    print("\n6. Updated Infrastructure Files:")
    updated_files = [
        ("docker-compose.yaml", "data-collection:"),
        ("requirements.txt", "rq=="),
        ("Makefile", "datacollection:"),
        (".gitignore", "dump.rdb")
    ]
    
    for filepath, pattern in updated_files:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if pattern in content:
                print(f"✓ {filepath} (updated with {pattern})")
            else:
                print(f"✗ {filepath} - Missing expected content: {pattern}")
                all_valid = False
        else:
            print(f"✗ {filepath} - NOT FOUND")
            all_valid = False
    
    # Summary
    print("\n" + "=" * 60)
    if all_valid:
        print("✅ All files validated successfully!")
        print("\nImplementation Summary:")
        print("  - 10 core pipeline modules")
        print("  - 3 main service files")
        print("  - 2 configuration files")
        print("  - 6 documentation files")
        print("  - 1 example file")
        print("  - 4 infrastructure files updated")
        print("\nTotal: 24 files created/modified")
        print("Status: COMPLETE")
        return 0
    else:
        print("❌ Validation failed - some files are missing or invalid")
        return 1

if __name__ == "__main__":
    sys.exit(main())
