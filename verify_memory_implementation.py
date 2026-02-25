#!/usr/bin/env python3
"""
Quick verification script to check if all Memory API components are properly implemented.
Run this to verify the implementation is complete.
"""

import os
import sys
from pathlib import Path


def check_file_exists(filepath, description):
    """Check if a file exists."""
    path = Path(filepath)
    exists = path.exists()
    status = "✓" if exists else "✗"
    print(f"{status} {description}: {filepath}")
    return exists


def check_import(module_name, description):
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        print(f"✓ {description}: {module_name}")
        return True
    except ImportError as e:
        print(f"✗ {description}: {module_name} - {e}")
        return False


def main():
    """Verify the Memory API implementation."""
    print("=" * 70)
    print("Memory API Implementation Verification")
    print("=" * 70)
    
    all_checks = []
    
    print("\n### Core Service Files ###")
    all_checks.append(check_file_exists("memory_service.py", "Memory Service"))
    all_checks.append(check_file_exists("api_server.py", "API Server"))
    
    print("\n### Configuration Files ###")
    all_checks.append(check_file_exists("requirements.txt", "Requirements"))
    all_checks.append(check_file_exists("docker-compose.yaml", "Docker Compose"))
    all_checks.append(check_file_exists("configs/mem0-config.yaml", "Mem0 Config"))
    
    print("\n### Documentation Files ###")
    all_checks.append(check_file_exists("MEMORY_README.md", "README"))
    all_checks.append(check_file_exists("MEMORY_QUICKSTART.md", "Quick Start"))
    all_checks.append(check_file_exists("MEMORY_API_REFERENCE.md", "API Reference"))
    all_checks.append(check_file_exists("MEMORY_IMPLEMENTATION_SUMMARY.md", "Implementation Summary"))
    
    print("\n### Example & Test Files ###")
    all_checks.append(check_file_exists("examples/memory_example.py", "Example Script"))
    all_checks.append(check_file_exists("test_memory.py", "Test Suite"))
    
    print("\n### Python Dependencies Check ###")
    # Check if we can import the service
    all_checks.append(check_import("memory_service", "Memory Service Import"))
    
    # Check dependencies (non-critical)
    print("\n### Optional Dependency Checks (install with: pip install -r requirements.txt) ###")
    check_import("mem0", "Mem0 Library")
    check_import("redis", "Redis Library")
    check_import("qdrant_client", "Qdrant Client")
    check_import("sentence_transformers", "Sentence Transformers")
    
    print("\n" + "=" * 70)
    
    if all(all_checks):
        print("✓ All critical components verified successfully!")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Start services: docker compose up -d")
        print("3. Run tests: python test_memory.py")
        print("4. Try example: python examples/memory_example.py")
        print("\nDocumentation:")
        print("- Quick Start: MEMORY_QUICKSTART.md")
        print("- Full Docs: MEMORY_README.md")
        print("- API Reference: MEMORY_API_REFERENCE.md")
        return 0
    else:
        print("✗ Some components are missing. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
